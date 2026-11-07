"""Each party's software and data stay inside its trust boundary.

Quality attribute: isolation of the parties. A web app is the one party its
settings module names (web.hospital.settings, .practice or .startup) and reads
only its folder, DATA_DIR; it installs, migrates and serves only its own
party's apps. Code under web/
imports from the training package only ml.cohort and ml.dataset; the
hospital's also ml.final_model, ml.inference, ml.training_cohort, to write
the training cohort its laboratory director provides, and ml.validation, to
validate the final models it fetches, the startup's also
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
BASE_ENV = {
    name: value
    for name, value in os.environ.items()
    if name
    not in {
        "DJANGO_SETTINGS_MODULE",
        "DATA_DIR",
        "MESSAGING_ADDRESS",
    }
}


def settings_of(party: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """The party's settings, loaded in a process of their own: the database's
    path, then the final models' folder."""
    code = (
        "from django.conf import settings;"
        " print(settings.DATABASES['default']['NAME']); print(settings.FINAL_MODELS_DIR)"
    )
    return subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        cwd=ROOT,
        env={**BASE_ENV, "DJANGO_SETTINGS_MODULE": f"web.{party}.settings", **env},
        capture_output=True,
        text=True,
    )


PARTIES = ["hospital", "practice", "startup"]


@pytest.mark.parametrize("party", PARTIES)
def test_a_partys_database_lives_in_its_folder(tmp_path: Path, party: str) -> None:
    """Pass: the party's database is DATA_DIR's web.sqlite3."""
    result = settings_of(party, {"DATA_DIR": str(tmp_path)})
    assert result.stdout.splitlines()[0] == str(tmp_path / "web.sqlite3"), result.stderr


def test_the_startup_keeps_its_final_models_in_its_folder(tmp_path: Path) -> None:
    """Pass: the startup's final models are in DATA_DIR's final-models."""
    result = settings_of("startup", {"DATA_DIR": str(tmp_path)})
    assert result.stdout.splitlines()[1] == str(tmp_path / "final-models")


@pytest.mark.parametrize("party", PARTIES)
def test_without_a_folder_a_party_keeps_its_data_in_the_checkouts(party: str) -> None:
    """A checkout without DATA_DIR (development, the tests) is still one party
    with a folder of its own. Pass: its database is .data/<party>/web.sqlite3."""
    result = settings_of(party, {})
    expected = ROOT / ".data" / party / "web.sqlite3"
    assert result.stdout.splitlines()[0] == str(expected), result.stderr


def seed(party: str, env: dict[str, str], nhanes: Path) -> None:
    """The party's demo accounts and records (python -m demo.seed); the startup
    seeds no participants, so it takes no NHANES file."""
    arguments = [] if party == "startup" else ["--nhanes", str(nhanes)]
    subprocess.run(
        [sys.executable, "-m", "demo.seed", party, *arguments],
        check=True,
        cwd=ROOT,
        env={
            **BASE_ENV,
            "DJANGO_SETTINGS_MODULE": f"web.{party}.settings",
            "DJANGO_DEBUG": "1",
            **env,
        },
        capture_output=True,
    )


def run_manage(party: str, env: dict[str, str], *args: str) -> None:
    subprocess.run(
        [sys.executable, "manage.py", *args],
        check=True,
        cwd=ROOT,
        env={
            **BASE_ENV,
            "DJANGO_SETTINGS_MODULE": f"web.{party}.settings",
            "DJANGO_DEBUG": "1",
            **env,
        },
        capture_output=True,
    )


def tables_after_migrating(party: str, folder: Path) -> set[str]:
    """The tables of a `party` web app's database in `folder`, once migrated."""
    run_manage(party, {"DATA_DIR": str(folder)}, "migrate", "-v0")
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
    """Pass: once migrated, the party's database has its own table and no table
    of another party's apps."""
    tables = tables_after_migrating(party, tmp_path)
    assert own in tables
    assert not [table for table in tables if table.startswith(others)]


# Each seeded account opens its role's pages in the party's own deployment.
SMOKE = """
from django.test import Client
from django.urls import reverse
from web.shared.accounts.models import User
from web.shared.accounts.roles import Role, role_of

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
    ("party", "users"),
    [
        ("hospital", {"director", "staff"}),
        ("practice", {"doctor"}),
        ("startup", {"data-scientist"}),
    ],
)
def test_every_page_of_a_party_loads_in_its_own_web_app(
    tmp_path: Path, party: str, users: set[str]
) -> None:
    """Pass: with only its own apps installed, every page of each seeded
    account's role answers 200."""
    from tests.conftest import nhanes_rows

    nhanes = tmp_path / "nhanes.csv"
    nhanes_rows().to_csv(nhanes, index=False)
    env = {"DATA_DIR": str(tmp_path)}
    run_manage(party, env, "migrate", "-v0")
    seed(party, env, nhanes)
    result = subprocess.run(
        [sys.executable, "manage.py", "shell", "-c", SMOKE],
        check=True,
        cwd=ROOT,
        env={
            **BASE_ENV,
            "DJANGO_SETTINGS_MODULE": f"web.{party}.settings",
            "DJANGO_ALLOWED_HOSTS": "testserver",
            **env,
        },
        capture_output=True,
        text=True,
    )
    pages = [
        line.split() for line in result.stdout.splitlines() if line.count(" ") == 2
    ]
    assert {username for username, _, _ in pages} == users
    assert [page for page in pages if page[2] != "200"] == []


def test_a_colour_without_a_vendored_pico_theme_is_refused() -> None:
    result = settings_of("hospital", {"PARTY_COLOUR": "chartreuse"})
    assert result.returncode != 0
    assert "PARTY_COLOUR" in result.stderr


def setting(party: str, name: str, env: dict[str, str]) -> str:
    code = f"from django.conf import settings; print(settings.{name})"
    return subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        cwd=ROOT,
        env={**BASE_ENV, "DJANGO_SETTINGS_MODULE": f"web.{party}.settings", **env},
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.mark.parametrize("party", PARTIES)
def test_each_party_has_its_own_cookies(tmp_path: Path, party: str) -> None:
    """Browsers share cookies across ports, and the demo runs every party on
    127.0.0.1. Pass: the session and CSRF cookies are named after the party's
    folder, so one party's login never replaces another's."""
    folder = tmp_path / "uz-leuven"
    folder.mkdir()
    env = {"DATA_DIR": str(folder)}
    assert setting(party, "SESSION_COOKIE_NAME", env) == "sessionid-uz-leuven"
    assert setting(party, "CSRF_COOKIE_NAME", env) == "csrftoken-uz-leuven"
