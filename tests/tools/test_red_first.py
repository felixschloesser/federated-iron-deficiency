"""Checks for .claude/red_first.py: which tests a Red: commit makes fail, and
whether only new ones do."""

import red_first

PYTEST_RUN = """\
..F.E                                                                    [100%]
=========================== short test summary info ============================
FAILED tests/scenarios/test_lab.py::test_a_new_scenario[one] - AssertionError
ERROR tests/tools/test_new.py - ModuleNotFoundError: No module named 'gone'
1 failed, 3 passed, 1 error in 0.12s
"""

PYTEST_COLLECTION = """\
tests/scenarios/test_lab.py::test_an_old_scenario
tests/tools/test_audit.py::test_clean_tree_has_no_findings

2 tests collected in 0.05s
"""


def test_failing_tests_are_read_from_the_summary() -> None:
    assert red_first.failing_tests(PYTEST_RUN) == {
        "tests/scenarios/test_lab.py::test_a_new_scenario[one]",
        "tests/tools/test_new.py",
    }


def test_collected_tests_are_the_ids_only() -> None:
    assert red_first.collected_tests(PYTEST_COLLECTION) == {
        "tests/scenarios/test_lab.py::test_an_old_scenario",
        "tests/tools/test_audit.py::test_clean_tree_has_no_findings",
    }


def test_only_new_tests_failing_is_red_first() -> None:
    before = red_first.collected_tests(PYTEST_COLLECTION)
    failing = red_first.failing_tests(PYTEST_RUN)
    assert red_first.problems(failing, before, changed=set()) == []


def test_a_test_in_a_changed_module_may_fail() -> None:
    before = {"tests/scenarios/test_lab.py::test_an_old_scenario"}
    failing = {"tests/scenarios/test_lab.py::test_an_old_scenario"}
    changed = {"tests/scenarios/test_lab.py"}
    assert red_first.problems(failing, before, changed) == []


def test_a_changed_feature_changes_the_modules_that_load_it() -> None:
    modules = {
        "tests/hospital/test_lab.py": 'scenarios("hospital/lab.feature")\n',
        "tests/practice/test_lab.py": 'scenarios("practice/lab.feature")\n',
        "tests/tools/test_audit.py": "import audit\n",
    }
    touched = [
        "features/hospital/lab.feature",
        "tests/tools/test_audit.py",
        "web/views.py",
    ]
    assert red_first.changed_modules(touched, modules) == {
        "tests/hospital/test_lab.py",
        "tests/tools/test_audit.py",
    }


def test_an_old_test_failing_is_reported() -> None:
    before = {"tests/scenarios/test_lab.py::test_an_old_scenario"}
    failing = {"tests/scenarios/test_lab.py::test_an_old_scenario"}
    assert red_first.problems(failing, before, changed=set()) == [
        (
            "tests/scenarios/test_lab.py::test_an_old_scenario fails, but it is neither"
            " new nor changed"
        )
    ]


def test_a_module_that_existed_before_is_not_new() -> None:
    before = {"tests/tools/test_audit.py::test_clean_tree_has_no_findings"}
    assert red_first.problems({"tests/tools/test_audit.py"}, before, set()) == [
        "tests/tools/test_audit.py fails, but it is neither new nor changed"
    ]


def test_no_failing_test_is_reported() -> None:
    assert red_first.problems(set(), set(), set()) == ["no test fails"]
