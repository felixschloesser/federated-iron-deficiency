"""Each party's software and data stay inside its trust boundary.

Quality attribute: isolation of the parties. A web app is the one party PARTY
names (hospital, practice or startup) and reads only its folder, DATA_DIR; it
installs, migrates and serves only its own party's apps. Code under web/
imports from the training package only ml.cohort and ml.dataset; the
hospital's also ml.final_model, ml.inference and ml.training_cohort, to write
the training cohort its laboratory director provides, the startup's also
ml.final_model, to read its final models, never to screen (the audit checks
that). Each test's docstring states its pass/fail measure."""

import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

import pytest

pytestmark = pytest.mark.subprocess

ROOT = Path(__file__).resolve().parents[3]
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


def tables_after_migrating_and_seeding(party: str, folder: Path) -> set[str]:
    """The tables of a `party` web app's database in `folder`, once it has
    migrated and seeded it."""
    from tests.conftest import nhanes_rows

    nhanes = folder / "nhanes.csv"
    nhanes_rows().to_csv(nhanes, index=False)
    env = {"PARTY": party, "DATA_DIR": str(folder)}
    command = SEED_COMMANDS[party]
    run_manage(env, "migrate", "-v0")
    run_manage(env, command, *seed_arguments(command, nhanes))
    with closing(sqlite3.connect(folder / "web.sqlite3")) as database:
        return {
            name
            for (name,) in database.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }


@pytest.mark.parametrize(
    ("party", "own", "others"),
    [
        ("hospital", "lab_testrequest", ("practice_", "training_")),
        (
            "practice",
            "practice_patient",
            ("lab_", "nhanes_", "deployment_", "cohort_", "training_"),
        ),
        (
            "startup",
            "accounts_user",
            ("lab_", "nhanes_", "deployment_", "cohort_", "practice_"),
        ),
    ],
)
def test_a_partys_database_holds_only_its_own_partys_tables(
    tmp_path: Path, party: str, own: str, others: tuple[str, ...]
) -> None:
    """Pass: once migrated and seeded, the party's database has its own table
    and no table of another party's apps."""
    tables = tables_after_migrating_and_seeding(party, tmp_path)
    assert own in tables
    assert not [table for table in tables if table.startswith(others)]


def refuses_to_start(result: subprocess.CompletedProcess[str], setting: str) -> None:
    assert result.returncode != 0
    assert setting in result.stderr


def test_a_web_app_refuses_a_database_outside_its_partys_folder(
    tmp_path: Path,
) -> None:
    """Pass: a hospital web app whose settings name a database elsewhere does not
    start, naming DATA_DIR."""
    env = {"PARTY": "hospital", "DATA_DIR": str(tmp_path), "DATABASE_NAME": "other"}
    refuses_to_start(database_path(env), "DATA_DIR")


def test_a_web_app_is_a_party_the_code_knows(tmp_path: Path) -> None:
    """Pass: a web app whose settings name the party "clinic" does not start,
    naming PARTY."""
    refuses_to_start(
        database_path({"PARTY": "clinic", "DATA_DIR": str(tmp_path)}), "PARTY"
    )


def test_a_web_app_keeps_its_data_in_a_folder_of_its_own() -> None:
    """Pass: a hospital web app whose settings name no folder does not start,
    naming DATA_DIR."""
    refuses_to_start(database_path({"PARTY": "hospital"}), "DATA_DIR")


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
def test_every_page_of_a_party_loads_in_its_own_web_app(
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
