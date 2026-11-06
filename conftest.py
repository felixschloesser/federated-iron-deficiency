"""Which tests a run collects: one party's (tests/<party>/) when --ds names that
party's settings, else every test outside the party folders. Each party's web
app is its own Django project at run time, so no run holds two parties."""

import os
from pathlib import Path

import pytest

TESTS = Path(__file__).parent / "tests"
PARTIES = {"hospital", "practice", "startup"}


def pytest_ignore_collect(collection_path: Path, config: pytest.Config) -> bool | None:
    settings = config.getoption("ds", default=None) or os.environ.get(
        "DJANGO_SETTINGS_MODULE", ""
    )
    party = settings.removeprefix("web.settings.") if settings else None
    if collection_path.parent == TESTS and collection_path.name in PARTIES:
        return collection_path.name != party
    if collection_path.parent == TESTS and party is not None:
        # The shared tests run once, in the run without a party.
        return collection_path.name not in {"__init__.py", "conftest.py"}
    return None
