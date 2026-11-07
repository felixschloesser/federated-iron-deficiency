"""Privacy tests: plain pytest, one test per threat and pass/fail measure, each
named in the test's docstring (.claude/CLAUDE.md).

A privacy test checks the system as deployed, never in this process (each
party's web app is a Django project of its own):

- In containers, against the running demo: the fixtures `compose`, `flower`,
  `superlink`, `hospital_app` and `proxy`, and `probe()` from
  tests/compose_project.py. Mark such a test `@pytest.mark.containers`.
- In a process of its own, as one party: `manage.py` under
  `DJANGO_SETTINGS_MODULE=web.settings.<party>` with a `DATA_DIR` of the
  test's (tests/quality/security/test_party_isolation.py shows how). Mark such
  a test `@pytest.mark.subprocess`.
"""
