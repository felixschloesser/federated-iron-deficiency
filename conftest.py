"""Which tests a run collects. Each party's web app is its own Django project at
run time, so no run holds two parties: a folder named after a party, anywhere
under tests/, runs only under that party's settings (--ds=web.<party>.settings).

Plain `pytest` runs the tests outside the party folders; each party's run is
`pytest --ds=web.<party>.settings`."""

import os
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
PARTIES = ("hospital", "practice", "startup")


def party_of(config: pytest.Config) -> str | None:
    settings = config.getoption("ds", default=None) or os.environ.get(
        "DJANGO_SETTINGS_MODULE", ""
    )
    return settings.removeprefix("web.").removesuffix(".settings") or None


def pytest_ignore_collect(collection_path: Path, config: pytest.Config) -> bool | None:
    parts = collection_path.relative_to(ROOT).parts
    if parts[:1] != ("tests",):
        return None
    folder = next((part for part in parts if part in PARTIES), None)
    party = party_of(config)
    if party is None:
        return True if folder else None
    if folder is not None:
        return folder != party
    # Outside the party folders a party's run only walks down to them.
    if collection_path.is_dir():
        return None
    return collection_path.name not in {"__init__.py", "conftest.py"}


def pytest_terminal_summary(
    terminalreporter: pytest.TerminalReporter, config: pytest.Config
) -> None:
    """A run under no party's settings leaves each party's tests out: say so."""
    if party_of(config) is None:
        terminalreporter.write_line(
            "Party tests not run: run each party's with"
            f" --ds=web.<party>.settings ({', '.join(PARTIES)}); see README, Tests."
        )


# What only a run under a party's settings provides.
DJANGO_FIXTURES = {"db", "transactional_db", "settings", "client", "django_db_setup"}


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """A test outside the party folders that needs Django would be skipped
    quietly ("no Django settings"): stop the run instead."""
    if party_of(config) is not None:
        return
    needing = [
        item
        for item in items
        if item.get_closest_marker("django_db")
        or DJANGO_FIXTURES & set(getattr(item, "fixturenames", ()))
    ]
    if needing:
        raise pytest.UsageError(
            "These tests need a party's Django settings:\n"
            + "\n".join(f"  {item.nodeid}: {remedy(item.path)}" for item in needing)
        )


def remedy(path: Path) -> str:
    parts = path.relative_to(ROOT).parts
    folder = next((part for part in parts if part in PARTIES), None)
    if folder is None:
        return "move it into a folder named after the party"
    return f"run it with --ds=web.{folder}.settings"
