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


# What only a run under a party's settings provides.
DJANGO_FIXTURES = {"db", "transactional_db", "settings", "client", "django_db_setup"}


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """A test outside the party folders that needs Django would be skipped
    quietly ("no Django settings"): stop the run instead."""
    settings = config.getoption("ds", default=None) or os.environ.get(
        "DJANGO_SETTINGS_MODULE"
    )
    if settings:
        return
    needing = [
        item.nodeid
        for item in items
        if item.get_closest_marker("django_db")
        or DJANGO_FIXTURES & set(getattr(item, "fixturenames", ()))
    ]
    if needing:
        raise pytest.UsageError(
            "These tests need a party's Django settings; move them to"
            " tests/<party>/: " + ", ".join(needing)
        )
