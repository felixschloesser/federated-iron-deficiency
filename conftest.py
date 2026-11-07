"""Which tests a run collects. Each party's web app is its own Django project at
run time, so no run holds two parties: a folder named after a party, anywhere
under tests/, runs only under that party's settings (--ds=web.<party>.settings).

Plain `pytest` runs everything: the tests outside the party folders here, then
each party's in a pytest of its own."""

import os
import subprocess
import sys
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
    if parts[:1] != ("tests",) and parts[:2] != (".claude", "tests"):
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


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """After the tests outside the party folders, each party's, unless the run
    named its tests or a party."""
    config = session.config
    if party_of(config) is not None or config.args_source == config.ArgsSource.ARGS:
        return
    statuses = [exitstatus]
    capture = config.pluginmanager.getplugin("capturemanager")
    with capture.global_and_fixture_disabled():
        for party in PARTIES:
            sys.stdout.flush()
            arguments = [*config.invocation_params.args, f"--ds=web.{party}.settings"]
            statuses.append(
                subprocess.run(
                    [sys.executable, "-m", "pytest", *arguments], check=False
                ).returncode
            )
    # 5 is "no tests collected", as under -m containers for a party.
    failed = [status for status in statuses if status not in (0, 5)]
    session.exitstatus = failed[0] if failed else min(statuses)


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
