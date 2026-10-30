"""Settings keep a hospital's web app inside its own folder (spec R21)."""

import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BASE_ENV = {
    name: value
    for name, value in os.environ.items()
    if name
    not in {"DATABASE_NAME", "HOSPITAL_DIR", "PRACTICE_DIR", "MESSAGING_ADDRESS"}
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
    result = database_path({"HOSPITAL_DIR": str(tmp_path)})
    assert result.stdout.strip() == str(tmp_path / "web.sqlite3")


def test_a_database_elsewhere_is_refused(tmp_path: Path) -> None:
    result = database_path({"HOSPITAL_DIR": str(tmp_path), "DATABASE_NAME": "other"})
    assert result.returncode != 0
    assert "HOSPITAL_DIR" in result.stderr


def test_a_practice_keeps_its_database_in_its_own_folder(tmp_path: Path) -> None:
    result = database_path({"PRACTICE_DIR": str(tmp_path)})
    assert result.stdout.strip() == str(tmp_path / "web.sqlite3")


def test_a_deployment_is_one_party(tmp_path: Path) -> None:
    result = database_path(
        {"HOSPITAL_DIR": str(tmp_path / "h"), "PRACTICE_DIR": str(tmp_path / "p")}
    )
    assert result.returncode != 0
    assert "PRACTICE_DIR" in result.stderr


def test_only_a_practice_sends_messages(tmp_path: Path) -> None:
    result = database_path(
        {"HOSPITAL_DIR": str(tmp_path), "MESSAGING_ADDRESS": "127.0.0.1:8443"}
    )
    assert result.returncode != 0
    assert "MESSAGING_ADDRESS" in result.stderr


def run_manage(env: dict[str, str], *args: str) -> None:
    subprocess.run(
        [sys.executable, "manage.py", *args],
        check=True,
        cwd=ROOT,
        env={**BASE_ENV, "DJANGO_DEBUG": "1", **env},
        capture_output=True,
    )


@pytest.mark.parametrize(
    ("folder", "command", "own", "others"),
    [
        ("HOSPITAL_DIR", "seed_hospital", "lab_laborder", ("practice_",)),
        (
            "PRACTICE_DIR",
            "seed_practice",
            "practice_patient",
            ("lab_", "nhanes_", "deployment_"),
        ),
    ],
)
def test_a_party_holds_only_its_own_tables(
    tmp_path: Path, folder: str, command: str, own: str, others: tuple[str, ...]
) -> None:
    """A hospital has no table for patients; a practice none for lab orders,
    analyser values or final models (R21)."""
    from tests.test_seed_demo import nhanes_rows

    nhanes = tmp_path / "nhanes.csv"
    nhanes_rows().to_csv(nhanes, index=False)
    env = {folder: str(tmp_path)}
    run_manage(env, "migrate", "-v0")
    run_manage(env, command, "--nhanes", str(nhanes))
    with closing(sqlite3.connect(tmp_path / "web.sqlite3")) as database:
        tables = {
            name
            for (name,) in database.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert own in tables
    assert not [table for table in tables if table.startswith(others)]
