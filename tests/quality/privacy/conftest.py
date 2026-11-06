"""Privacy tests: plain pytest, one test per threat and pass/fail measure, each
named in the test's docstring (.claude/CLAUDE.md).

What a test here can build on:

- The hospital's side, in this process: `from tests.hospital.conftest import
  receive_lab_order, make_tube, make_practice, make_laboratory_director,
  make_laboratory_staff_member, write_final_model`.
- The general practitioner's side, in this process: `from
  tests.practice.conftest import make_patient, collect_and_order,
  make_general_practitioner`; the stand-in for a hospital's lab-order endpoint
  is the `fake_laboratory` fixture below.
- The startup's side: `from tests.startup.conftest import make_data_scientist`.
- The running demo, with a Docker engine: the fixtures `compose`, `flower`,
  `superlink`, `hospital_app` and `probe()` from tests/compose_project.py. Mark
  such a test `@pytest.mark.containers`; one that starts a process of its own,
  `@pytest.mark.subprocess`.
"""

from tests.practice.conftest import fake_laboratory

__all__ = ["fake_laboratory"]
