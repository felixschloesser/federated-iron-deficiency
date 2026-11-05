"""Every scenario module stands on its own: it declares its database access."""

import importlib
from pathlib import Path

import pytest

MODULES = sorted(
    path.stem
    for path in Path(__file__).parent.glob("test_*.py")
    if path.stem != "test_modules"
)


@pytest.mark.parametrize("name", MODULES)
def test_a_scenario_module_declares_its_database_access(name: str) -> None:
    # Without the mark a module passes only after another one has created the
    # test database, and fails when run alone.
    module = importlib.import_module(f"tests.scenarios.{name}")
    marks = getattr(module, "pytestmark", [])
    marks = marks if isinstance(marks, list) else [marks]
    assert any(mark.name == "django_db" for mark in marks), name
