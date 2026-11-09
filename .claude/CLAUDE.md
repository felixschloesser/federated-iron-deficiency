# Working in this repository

Server-rendered Django. No JS frontend: every page is a template, every mutation a form POST.

Several sessions work in this repository at the same time.

- The repository-root checkout stays on `main`. Never check out another branch there, never reset it, never commit someone else's uncommitted changes from it. Do all branch work in a worktree under `.claude/worktrees/` (`git worktree add .claude/worktrees/<name> -b <name> main`).
- "Merge main" means the `main` ref. Before merging into main, check `git branch --show-current` in the checkout you merge in.
- Never use a bare `git stash`; the stash is shared by every worktree.
- Each party's web app is its own Django project at run time: `DJANGO_SETTINGS_MODULE=web.<party>.settings` (hospital, practice, startup) for `manage.py`, `runserver` and the tests. Each worktree keeps each party's data in its own `.data/<party>/` (gitignored), unless `DATA_DIR` names another folder; give each party's `runserver` its own port. Never point two worktrees at one folder.
- The session that merges a branch removes it: `git worktree remove .claude/worktrees/<name>` and `git branch -d <name>`.
- Commit as soon as each slice is green. Keep an untracked `PROGRESS.md` in the worktree: last step done, next step, open questions. An interrupted run reads it first.

## Gates

Commit only when all of these exit 0:

```
uv run --frozen ruff format --check .
uv run --frozen ruff check .
uv run --frozen mypy --strict . .claude/audit.py .claude/red_first.py
for party in hospital practice startup; do DJANGO_SETTINGS_MODULE=web.$party.settings uv run --frozen python -W error manage.py check; done
for party in hospital practice startup; do DJANGO_SETTINGS_MODULE=web.$party.settings uv run --frozen python manage.py makemigrations --check --dry-run; done
uv run --frozen pytest -W error
uv run --frozen python .claude/audit.py
```

- Run every gate through `uv run --frozen`, never with a stale `.venv`. Plain pytest runs the tests outside the party folders without Django settings, then each party's (a folder named after the party, anywhere under `tests/`) in a pytest of its own under `--ds=web.<party>.settings` (`conftest.py`). With `DJANGO_SETTINGS_MODULE` set in the shell, it runs only that party's tests: unset it.
- Merge gate: `uv run --frozen pytest -W error -m containers` must also exit 0 when a branch touches what the images or containers are made of, or the tests that run them: compose, Docker files, `.dockerignore`, `web/shared/settings.py`, `web/<party>/settings.py`, `demo/`, `ml/`, `pyproject.toml`, `uv.lock`, `tests/compose_project.py` or a test marked `containers`. Other branches merge without it.
- Merge gate: `uv run --frozen pytest -W error -m nhanes` must also exit 0 when a branch touches what the model learns or how: `ml/`, `web/hospital/cohort/models.py`, `pyproject.toml`'s `[tool.flwr.app.config]`, or a test marked `nhanes`. It trains on the pinned NHANES revision (downloaded once).

- Zero warnings. Never suppress one (`# noqa`, `# type: ignore`, `filterwarnings`); fix the root cause. Generated code (protoc's `*_pb2*`) is excluded from ruff instead: excluded, not suppressed; regenerate it, never patch it. If the fix is genuinely unclear, stop and report with a recommendation.
- `.claude/audit.py` fails on any finding.
- Under machine load, rerun a timed-out test once and report it.

## Core and supporting code

Rigour goes where the assessment is decided.

- **Core**: what crosses a party boundary (the messages in `web/shared/grpc/`, each party's `grpc_server` and `grpc_client` modules, what a lab order, lab report or final model carries), who logs in where, screening (`web/hospital/lab/`, `web/hospital/deployment/`), the training cohort (`web/hospital/cohort/`) and `ml/`. All the rules below apply: scenarios, glossary words, a guard with its own code for each condition, constraints.
- **Supporting**: everything else, such as the ordering and index pages, the training run list, seeding and `demo/`. Plain Django: view tests (status, redirect, error codes) are enough, and a scenario only where another party or the report relies on the behaviour. Red first, the gates and the design rules still apply.

## Vocabulary first

- Before any scenario that introduces or renames a domain concept: a term table (term | source | why chosen | rejected terms). A term without a source stops the draft; report it.
- Glossary entries (each party's in `web/<party>/glossary.toml`, the words more than one party uses in `web/shared/glossary.toml`; one table per term with `meaning` and `source`, for readers) change in the same commit as the code; the words a term replaced and the date the team decided it go in `.claude/glossary_record.toml` (`rejected`, `decided`). The audit fails on a glossary outside a party's folder or `web/shared/`, on a term without a meaning or source, on a record term in no glossary, and on code citing `glossary.toml` without its folder. Model, form, template and copy use the glossary's words; the domain experts' words win over developer words.

## Red first

- Each behaviour slice lands as two commits: `Red: …` with only the scenarios and steps (only the new scenarios fail), then the code commit (all green).
- If code must come first (a removed field breaks imports), end the slice by disabling each new guard and confirming its scenarios go red; put the table (guard → scenarios) in the commit message.
- Gates do not run on `Red:` commits.
- Before merging, `uv run --frozen python .claude/red_first.py` (default range `main..HEAD`) exits 0: each `Red:` commit fails at least one test, and only tests that are new or that it changed (their module, or a feature file the module loads).

## Design rules

- **Derive, don't list.** "Which X belong to Y" over a closed set is a `match` on a `TextChoices`/`Enum` ending in `assert_never(value)`, never a list or dict literal of members. The one exception: each party's settings (`web/<party>/settings.py`) write out its `INSTALLED_APPS` and `ROLES`; the audit checks every app in a party's folder is installed by that party alone, and every `Role` logs in to exactly one party. Every mapping that crosses layers (choice → URL name, choice → template section) has a test parametrised over every member asserting it lands somewhere.
- **Absence is `None`.** `X | None`, never a placeholder choice like `UNDECIDED`. `null=True` only where absence is a real state.
- **Domain logic lives on the models.** Behaviour of one row is a model method; operations on a table and named queries are methods of the model's custom QuerySet or Manager; a rule the database can hold is a constraint with `violation_error_code`. Code that is not ORM (model files, gRPC) lives in a module named after what it does. Views stay thin: parse the form, call one model or manager method, redirect or re-render.
- **Writes are atomic.** A model or manager method that writes is decorated `@transaction.atomic`; the audit treats a call to one as a write.
- **Inject the clock.** Methods that record a time take `now` as an argument; only entry points (views, management commands, gRPC handlers) call `timezone.now()`.
- **One error per failing condition.** Each condition a user or another party can cause gets a guard that raises its own `ValidationError` with its own `code`, attached to its field (`add_error(field, …)`); non-field errors only for cross-field conditions. A condition no form or message can produce is held by a database constraint alone, without its own code or scenario.
- **No capability without a path to it.** Every writing model or manager method is reachable from a view; every view from the URLconf and a link or form on a page.
- **POST-redirect-GET.** Every mutation is a POST that redirects on success. GET never mutates.
- Code rules: no bare `assert` outside tests; no `except Exception` without re-raise; no single-letter names.
- Outside `tests/`, a module or class docstring may name its feature file, once; functions, methods and comments do not (the audit checks).

## Templates

- Pages are built only from the shared includes (`web/shared/templates/includes/`: base layout, index header, action row, archive/restore with the refusal beside the action, form layout, error summary). A missing piece goes into includes/, not the page.
- Only CSS classes defined in the vendored stylesheet or `web/shared/static/css/`. The audit checks `class="…"` in the templates.
- Conditional controls (show only when the recorded facts make them applicable) are decided in the view or a query function and tested there, not by rendering.
- In tests, `string_if_invalid` fails the test; a missing variable never renders blank.
- `|safe` and `mark_safe` only with an entry and reason in the audit allowlist. No `csrf_exempt`.

## Tests

- The requirements are the scenarios: `features/<party>/` for each party's behaviour (bound in `tests/<party>/`, which imports no other party's code; the audit checks), `features/` for what crosses parties, each scenario ending in a true-or-false response measure. Folders say what a test checks, markers how it runs: `tests/e2e/` holds the flows through the running demo (the folder marks them `containers`), `tests/quality/security/` the security quality attributes at whatever tier each needs, marked `containers` where it needs Docker; a test that starts a process of its own is marked `subprocess`, so the quick loop `pytest -m "not containers and not subprocess"` leaves it out (a `-m` replaces the default one). A docstring states the reason and may name the feature file.
- Quality tests are plain pytest, no Gherkin: `tests/quality/security/` and `tests/quality/privacy/`. Each test's docstring names the quality attribute or threat it covers and states its pass/fail measure in one sentence. The gates apply to them as to any code.
- Core domain behaviour: scenarios (pytest-bdd) against model and manager methods, not views.
- Views: Django test client, asserting status, redirect target, form error codes and `assertNumQueries` on index pages. No whole-page HTML snapshots, no sweeps rendering every page.
- One migration per slice, committed with the slice.

## Browser check before merge

A branch that changes templates or CSS is checked in a browser by a separate agent before merging: `runserver` on its own port from the branch's worktree, with a checklist from the branch's scenarios plus what tests cannot see (placement, focus order, keyboard, scrolling, narrow and wide widths). The results go in the merge commit body; screenshots go under the gitignored `.ui-audit/<branch>/` and are never committed. Defects go back to the branch. A branch without UI change says so.

## Report back

Commits; scenarios added, changed or deleted (and what covers a deleted one); red-first evidence; what was not checked.
