"""Settings keep each party's web app inside its own folder: scenarios
(features/quality/party_isolation.feature), and the checks beside them."""

import os
import re
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

ROOT = Path(__file__).resolve().parents[2]
# Each party's seed command.
SEED_COMMANDS = {
    "hospital": "seed_hospital",
    "practice": "seed_practice",
    "startup": "seed_startup",
}
BASE_ENV = {
    name: value
    for name, value in os.environ.items()
    if name
    not in {
        "DATABASE_NAME",
        "PARTY",
        "DATA_DIR",
        "MESSAGING_ADDRESS",
    }
}


def database_path(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    code = (
        "from django.conf import settings; print(settings.DATABASES['default']['NAME'])"
    )
    return subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        cwd=ROOT,
        env={**BASE_ENV, "DJANGO_SETTINGS_MODULE": "web.settings", **env},
        capture_output=True,
        text=True,
    )


def test_the_database_lives_in_the_hospital_folder(tmp_path: Path) -> None:
    result = database_path({"PARTY": "hospital", "DATA_DIR": str(tmp_path)})
    assert result.stdout.strip() == str(tmp_path / "web.sqlite3")


def test_a_practice_keeps_its_database_in_its_own_folder(tmp_path: Path) -> None:
    result = database_path({"PARTY": "practice", "DATA_DIR": str(tmp_path)})
    assert result.stdout.strip() == str(tmp_path / "web.sqlite3")


def test_the_startup_keeps_its_database_and_final_models_in_its_folder(
    tmp_path: Path,
) -> None:
    env = {"PARTY": "startup", "DATA_DIR": str(tmp_path)}
    result = database_path(env)
    assert result.stdout.strip() == str(tmp_path / "web.sqlite3")
    final_models = setting("FINAL_MODELS_DIR", env)
    assert final_models == str(tmp_path / "final-models")


def seed_arguments(command: str, nhanes: Path) -> list[str]:
    """The startup seeds no participants, so it takes no NHANES file."""
    return [] if command == "seed_startup" else ["--nhanes", str(nhanes)]


def run_manage(env: dict[str, str], *args: str) -> None:
    subprocess.run(
        [sys.executable, "manage.py", *args],
        check=True,
        cwd=ROOT,
        env={**BASE_ENV, "DJANGO_DEBUG": "1", **env},
        capture_output=True,
    )


scenarios("quality/party_isolation.feature")


@given(
    parsers.parse("a {party} deployment in a folder of its own"),
    target_fixture="deployment",
)
def deployment(tmp_path: Path, party: str) -> dict[str, Any]:
    return {
        "env": {"PARTY": party, "DATA_DIR": str(tmp_path)},
        "command": SEED_COMMANDS[party],
        "folder": tmp_path,
    }


@when("it migrates and seeds its database")
def migrate_and_seed(deployment: dict[str, Any]) -> None:
    from tests.conftest import nhanes_rows

    folder = deployment["folder"]
    nhanes = folder / "nhanes.csv"
    nhanes_rows().to_csv(nhanes, index=False)
    env = deployment["env"]
    run_manage(env, "migrate", "-v0")
    run_manage(
        env, deployment["command"], *seed_arguments(deployment["command"], nhanes)
    )
    with closing(sqlite3.connect(folder / "web.sqlite3")) as database:
        deployment["tables"] = {
            name
            for (name,) in database.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }


@when("its settings name a database elsewhere")
def database_elsewhere(deployment: dict[str, Any]) -> None:
    deployment["result"] = database_path(
        {**deployment["env"], "DATABASE_NAME": "other"}
    )


@when(parsers.parse('its settings name the party "{party}"'))
def unknown_party(deployment: dict[str, Any], party: str) -> None:
    deployment["result"] = database_path({**deployment["env"], "PARTY": party})


@when("its settings name no folder")
def no_folder(deployment: dict[str, Any]) -> None:
    deployment["result"] = database_path({"PARTY": deployment["env"]["PARTY"]})


@then(parsers.parse('its database has the table "{own}"'))
def has_table(deployment: dict[str, Any], own: str) -> None:
    assert own in deployment["tables"]


@then(parsers.parse("its database has no table starting with {others}"))
def no_other_tables(deployment: dict[str, Any], others: str) -> None:
    prefixes = tuple(re.findall(r'"([^"]+)"', others))
    assert prefixes
    assert not [table for table in deployment["tables"] if table.startswith(prefixes)]


@then(parsers.parse('the web app does not start, naming "{setting}"'))
def does_not_start(deployment: dict[str, Any], setting: str) -> None:
    assert deployment["result"].returncode != 0
    assert setting in deployment["result"].stderr


# Each seeded account opens its role's pages in the party's own deployment.
SMOKE = """
from django.test import Client
from django.urls import reverse
from web.accounts.models import User
from web.accounts.roles import Role, role_of

for user in User.objects.order_by("username"):
    role = role_of(user)
    if role is None:
        continue
    client = Client()
    client.force_login(user)
    urls = [link["url"] for link in role.nav_links()]
    if role is Role.GENERAL_PRACTITIONER:
        from web.practice.models import Patient

        patient = Patient.objects.first()
        urls.append(reverse("practice:patient", kwargs={"pk": patient.pk}))
    for url in urls:
        status = client.get(url, secure=True).status_code
        print(user.username, url, status)
"""


@pytest.mark.parametrize(
    ("party", "command", "users"),
    [
        ("hospital", "seed_hospital", {"director", "staff"}),
        ("practice", "seed_practice", {"doctor"}),
        ("startup", "seed_startup", {"data-scientist"}),
    ],
)
def test_every_page_of_a_party_loads_in_its_own_deployment(
    tmp_path: Path, party: str, command: str, users: set[str]
) -> None:
    """Development serves every party from one database; this runs each party's
    pages with only its own apps installed."""
    from tests.conftest import nhanes_rows

    nhanes = tmp_path / "nhanes.csv"
    nhanes_rows().to_csv(nhanes, index=False)
    env = {"PARTY": party, "DATA_DIR": str(tmp_path)}
    run_manage(env, "migrate", "-v0")
    run_manage(env, command, *seed_arguments(command, nhanes))
    result = subprocess.run(
        [sys.executable, "manage.py", "shell", "-c", SMOKE],
        check=True,
        cwd=ROOT,
        env={**BASE_ENV, "DJANGO_ALLOWED_HOSTS": "testserver", **env},
        capture_output=True,
        text=True,
    )
    pages = [
        line.split() for line in result.stdout.splitlines() if line.count(" ") == 2
    ]
    assert {username for username, _, _ in pages} == users
    assert [page for page in pages if page[2] != "200"] == []


def test_a_colour_without_a_vendored_pico_theme_is_refused() -> None:
    result = database_path({"PARTY_COLOUR": "chartreuse"})
    assert result.returncode != 0
    assert "PARTY_COLOUR" in result.stderr


def setting(name: str, env: dict[str, str]) -> str:
    code = f"from django.conf import settings; print(settings.{name})"
    return subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        cwd=ROOT,
        env={**BASE_ENV, "DJANGO_SETTINGS_MODULE": "web.settings", **env},
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.mark.parametrize("party", ["hospital", "practice", "startup"])
def test_each_party_has_its_own_cookies(tmp_path: Path, party: str) -> None:
    # Browsers share cookies across ports, and the demo runs every party on
    # 127.0.0.1: one party's login must not replace another's session or token.
    folder = tmp_path / "uz-leuven"
    folder.mkdir()
    env = {"PARTY": party, "DATA_DIR": str(folder)}
    assert setting("SESSION_COOKIE_NAME", env) == "sessionid-uz-leuven"
    assert setting("CSRF_COOKIE_NAME", env) == "csrftoken-uz-leuven"


def test_a_development_checkout_keeps_djangos_cookie_names() -> None:
    assert setting("SESSION_COOKIE_NAME", {}) == "sessionid"
    assert setting("CSRF_COOKIE_NAME", {}) == "csrftoken"
