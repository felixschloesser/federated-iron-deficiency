"""Privacy tests: one test per privacy threat, plain pytest.

The rules:

- Each test's docstring names the threat it covers and states its pass/fail
  measure in one sentence.
- Test at the cheapest tier that fails when the property breaks:
  1. The contract or code itself, no database: a test here, beside this file
     (test_messages.py reads what the gRPC messages may carry).
  2. One party's Django app, in this process: a test in the folder named after
     the party (hospital/), which runs under that party's settings, with the
     `db` fixture.
  3. The running demo in containers, only when the answer depends on it: which
     network reaches what, what a mount allows. Mark it
     `@pytest.mark.containers`; tests/quality/security/test_running_containers.py
     shows the fixtures.
- A test that finds a real leak lands marked
  `@pytest.mark.xfail(strict=True, reason="<threat>: open, <what leaks>")`: the
  run stays green, the finding stays visible, and the test fails the day the
  leak is fixed, so the mark comes off.
- `uv run pytest` runs every test, each party's under its settings; ruff and
  mypy --strict check tests as they check the code.
"""
