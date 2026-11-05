# Working in this repository

Server-rendered Django. No JS frontend: every page is a template, every mutation a form POST.

Several sessions work in this repository at the same time.

- The repository-root checkout stays on `main`. Never check out another branch there, never reset it, never commit someone else's uncommitted changes from it. Do all branch work in a worktree under `.claude/worktrees/` (`git worktree add .claude/worktrees/<name> -b <name> main`).
- "Merge main" means the `main` ref. Before merging into main, check `git branch --show-current` in the checkout you merge in.
- Never use a bare `git stash`; the stash is shared by every worktree.
- Each worktree has its own database (`DATABASE_NAME=<worktree name>`) and its own `runserver` port. Never point two worktrees at one database.
- The session that merges a branch removes it: `git worktree remove .claude/worktrees/<name>` and `git branch -d <name>`.
- Commit as soon as each slice is green. Keep an untracked `PROGRESS.md` in the worktree: last step done, next step, open questions. An interrupted run reads it first.

## Gates

Commit only when all of these exit 0:

```
uv run --frozen ruff format --check .
uv run --frozen ruff check .
uv run --frozen mypy --strict .
uv run --frozen python -W error manage.py check
uv run --frozen python manage.py makemigrations --check --dry-run
uv run --frozen pytest -W error
uv run --frozen python tools/audit.py
```

- Run every gate through `uv run --frozen`, never with a stale `.venv`.
- Merge gate: `uv run --frozen pytest -W error -m containers` must also exit 0 when a branch touches compose, Docker files, `.dockerignore`, `web/settings.py`, `demo/`, `pyproject.toml` or `uv.lock`, and always on the merge to `main`.

- Zero warnings. Never suppress one (`# noqa`, `# type: ignore`, `filterwarnings`); fix the root cause. If the fix is genuinely unclear, stop and report with a recommendation.
- `tools/audit.py` is a ratchet: its baseline may only go down. After `python tools/audit.py --update`, `git diff tools/` must show no increase.
- Under machine load, rerun a timed-out test once and report it.

## Vocabulary first

- Before any scenario that introduces or renames a domain concept: a term table (term | source | why chosen | rejected terms). A term without a source stops the draft; report it.
- Glossary entries change in the same commit as the code, each with its source. Model, form, template and copy use the glossary's words; the domain experts' words win over developer words.

## Red first

- Each behaviour slice lands as two commits: `Red: …` with only the scenarios and steps (only the new scenarios fail), then the code commit (all green).
- If code must come first (a removed field breaks imports), end the slice by disabling each new guard and confirming its scenarios go red; put the table (guard → scenarios) in the commit message.
- Gates do not run on `Red:` commits.

## Design rules

- **Derive, don't list.** "Which X belong to Y" over a closed set is a `match` on a `TextChoices`/`Enum` ending in `assert_never(value)`, never a list or dict literal of members. Every mapping that crosses layers (choice → URL name, choice → template section) has a test parametrised over every member asserting it lands somewhere.
- **Absence is `None`.** `X | None`, never a placeholder choice like `UNDECIDED`. `null=True` only where absence is a real state.
- **Domain logic lives on the models.** Behaviour of one row is a model method; operations on a table and named queries are methods of the model's custom QuerySet or Manager; a rule the database can hold is a constraint with `violation_error_code`. Code that is not ORM (model files, messaging) lives in a module named after what it does. Views stay thin: parse the form, call one model or manager method, redirect or re-render.
- **Writes are atomic.** A model or manager method that writes is decorated `@transaction.atomic`; the audit treats a call to one as a write.
- **Inject the clock.** Methods that record a time take `now` as an argument; only entry points (views, management commands, gRPC handlers) call `timezone.now()`.
- **One error per failing condition.** Each guard raises its own `ValidationError` with its own `code`, attached to its field (`add_error(field, …)`); non-field errors only for cross-field conditions.
- **No capability without a path to it.** Every writing model or manager method is reachable from a view; every view from the URLconf and a link or form on a page.
- **POST-redirect-GET.** Every mutation is a POST that redirects on success. GET never mutates.
- Code rules: no bare `assert` outside tests; no `except Exception` without re-raise; no single-letter names; functions ≤100 lines, ≤5 parameters.

## Templates

- Pages are built only from the shared kit (`templates/kit/`: base layout, index header, action row, archive/restore with the refusal beside the action, form layout, error summary). A missing piece goes into the kit, not the page.
- Only CSS classes defined in the vendored stylesheet or `static/css/`. The audit checks `class="…"` in `templates/`.
- Conditional controls (show only when the recorded facts make them applicable) are decided in the view or a query function and tested there, not by rendering.
- In tests, `string_if_invalid` fails the test; a missing variable never renders blank.
- `|safe` and `mark_safe` only with an entry and reason in the audit allowlist. No `csrf_exempt`.

## Tests

- Domain behaviour: scenarios (pytest-bdd) against model and manager methods, not views.
- Views: Django test client, asserting status, redirect target, form error codes and `assertNumQueries` on index pages. No whole-page HTML snapshots, no sweeps rendering every page.
- One migration per slice, committed with the slice.

## Browser check before merge

A branch that changes templates or CSS is checked in a browser by a separate agent before merging: `runserver` on its own port from the branch's worktree, with a checklist from the branch's scenarios plus what tests cannot see (placement, focus order, keyboard, scrolling, narrow and wide widths). The results go in the merge commit body; screenshots go under the gitignored `.ui-audit/<branch>/` and are never committed. Defects go back to the branch. A branch without UI change says so.

## Report back

Commits; scenarios added, changed or deleted (and what covers a deleted one); red-first evidence; audit baseline moves explained; what was not checked.

## To build

These are referenced above but do not exist yet: `tools/audit.py` (derive-don't-list, CSS classes, `|safe` allowlist, kit-only templates, glossary sources, GET-mutation) and a `tools/red_first.py` that checks each `Red:` commit in a temporary worktree.
