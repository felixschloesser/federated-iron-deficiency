"""Every scenario module stands on its own: it declares its database access."""

import ast
from pathlib import Path

import pytest

TESTS = Path(__file__).parent
# Each party's modules that bind scenarios of features/.
MODULES = sorted(
    path.relative_to(TESTS).as_posix()
    for party in ("hospital", "practice", "startup")
    for path in (TESTS / party).glob("test_*.py")
    if "scenarios(" in path.read_text()
)


def marks(path: Path) -> list[str]:
    """The source of each mark the module's pytestmark names, read without
    importing it: each party's modules import only under that party's settings."""
    for node in ast.parse(path.read_text()).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "pytestmark"
            for target in node.targets
        ):
            values = (
                node.value.elts if isinstance(node.value, ast.List) else [node.value]
            )
            return [ast.unparse(value) for value in values]
    return []


@pytest.mark.parametrize("module", MODULES)
def test_a_scenario_module_declares_its_database_access(module: str) -> None:
    # Without the mark a module passes only after another one has created the
    # test database, and fails when run alone.
    assert any(
        mark.startswith("pytest.mark.django_db") for mark in marks(TESTS / module)
    ), module
