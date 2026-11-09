# Working in this repository

Server-rendered Django. No JS frontend: every page is a template, every mutation a form POST.

Several sessions work in this repository at the same time.

- The repository-root checkout stays on `main`. Never check out another branch there, never reset it, never commit someone else's uncommitted changes from it. Do all branch work in a worktree under `.claude/worktrees/` (`git worktree add .claude/worktrees/<name> -b <name> main`).
- "Merge main" means the `main` ref. Before merging into main, check `git branch --show-current` in the checkout you merge in.
- Never use a bare `git stash`; the stash is shared by every worktree.
- Each party's web app is its own Django project: `DJANGO_SETTINGS_MODULE=web.<party>.settings` (hospital, practice, startup) for `manage.py`, `runserver` and the tests. Each worktree keeps each party's data in its own `.data/<party>/` (gitignored) unless `DATA_DIR` names another folder; give each party's `runserver` its own port.
- The session that merges a branch removes it: `git worktree remove .claude/worktrees/<name>` and `git branch -d <name>`.
- Commit as soon as each slice is green. Keep an untracked `PROGRESS.md` in the worktree: last step done, next step, open questions. An interrupted run reads it first.

## Gates

Commit only when all of these exit 0 (with `DJANGO_SETTINGS_MODULE` unset):

```
uv run --frozen ruff format --check .
uv run --frozen ruff check .
uv run --frozen mypy --strict .
for party in hospital practice startup; do DJANGO_SETTINGS_MODULE=web.$party.settings uv run --frozen python -W error manage.py check; done
for party in hospital practice startup; do DJANGO_SETTINGS_MODULE=web.$party.settings uv run --frozen python manage.py makemigrations --check --dry-run; done
uv run --frozen pytest -W error
for party in hospital practice startup; do uv run --frozen pytest -W error --ds=web.$party.settings; done
```

- Before merging a branch that touches compose, Docker files, `.dockerignore`, settings, `demo/`, `ml/`, `pyproject.toml`, `uv.lock`, `tests/compose_project.py` or a `containers` test: the same pytest runs with `-m containers` also pass.
- Before merging a branch that touches `ml/`, `web/hospital/cohort/models.py`, `[tool.flwr.app.config]` or an `nhanes` test: `uv run --frozen pytest -W error -m nhanes` also passes.
- Zero warnings, none suppressed (`# noqa`, `# type: ignore`, `filterwarnings`): fix the cause. protoc's `*_pb2*` is excluded from ruff; regenerate it, never patch it. If the fix is unclear, stop and report.
- Under machine load, rerun a timed-out test once and report it.

## Code

- **Core** is what the assessment rests on: what crosses a party boundary (`web/shared/grpc/`, each party's `grpc_server` and `grpc_client`), who logs in where, screening (`web/hospital/lab/`, `web/hospital/deployment/`), the training cohort (`web/hospital/cohort/`) and `ml/`. Core behaviour has scenarios (pytest-bdd, `features/`) against model and manager methods. Everything else is plain Django with view tests (status, redirect, error codes).
- Write the failing test first; a behaviour lands with its tests in one commit, with its migration.
- Domain logic lives on models, querysets and managers; views parse the form, call one method, redirect or re-render. Writing methods are `@transaction.atomic`.
- Absence is `None`, never a placeholder choice; `null=True` only where absence is a real state. A setting that is always set is never optional.
- Methods that record a time take `now`; only views, commands and gRPC handlers call `timezone.now()`.
- Each condition a user or another party can cause raises its own `ValidationError` code on its field. A rule the database can hold is a constraint.
- Every mutation is a POST that redirects; GET never mutates.
- No bare `assert` outside tests, no `except Exception` without re-raise, no single-letter names, no `|safe`, `mark_safe` or `csrf_exempt`.
- Docstrings say what, then why, in plain sentences; a module docstring may name its feature file once. Use `GLOSSARY.md`'s words in models, forms, templates and copy.
- Pages extend the shared includes (`web/shared/templates/includes/`) and use the vendored Pico stylesheet's classes or `web/shared/static/css/`.

## Tests

- Each party's tests live in a folder named after it (`tests/<party>/`, `tests/quality/privacy/hospital/`) and import no other party's code (`tests/quality/security/test_boundaries.py`).
- `tests/e2e/` runs through the demo's containers; `tests/quality/security/` and `tests/quality/privacy/` hold one plain pytest per threat, its docstring stating the pass/fail measure. A test that needs Docker is marked `containers`, one that starts a process `subprocess`; the quick loop is `pytest -m "not containers and not subprocess"`.
- In tests, `string_if_invalid` fails the test. No whole-page HTML snapshots.
- A branch that changes templates or CSS gets a look in a browser before merging; say what was checked in the merge commit.

## Report back

Commits; scenarios added, changed or deleted (and what covers a deleted one); what was not checked.
