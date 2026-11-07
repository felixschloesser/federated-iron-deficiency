"""Migrations on databases the demo already holds."""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.subprocess

ROOT = Path(__file__).resolve().parents[2]


def migrate(practice: Path, *target: str) -> None:
    env = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "practice.settings",
        "DATA_DIR": str(practice),
        "DJANGO_DEBUG": "1",
    }
    subprocess.run(
        [sys.executable, str(ROOT / "manage.py"), "migrate", *target, "-v0"],
        env=env,
        check=True,
    )


def test_a_laboratory_folder_added_unique_is_removed_with_its_laboratories(
    tmp_path: Path,
) -> None:
    """A demo volume ran 0003 when it made the folder unique; 0004 must drop
    that unique column, laboratories kept, which SQLite cannot do in place."""
    migrate(tmp_path, "practice", "0002")
    database = sqlite3.connect(tmp_path / "web.sqlite3")
    with database:
        database.executemany(
            "INSERT INTO practice_laboratory (name, address) VALUES (?, ?)",
            [("UZ Leuven", "uz-leuven:8441"), ("AZ Diest", "az-diest:8441")],
        )
    migrate(tmp_path, "practice", "0003")
    indexes = database.execute("PRAGMA index_list(practice_laboratory)").fetchall()
    unique = [
        database.execute(f"PRAGMA index_info({index[1]!r})").fetchall()
        for index in indexes
        if index[2]
    ]
    assert any(columns[0][2] == "folder" for columns in unique)

    migrate(tmp_path)
    columns = database.execute("PRAGMA table_info(practice_laboratory)").fetchall()
    assert "folder" not in {column[1] for column in columns}
    names = database.execute("SELECT name FROM practice_laboratory ORDER BY name")
    assert [row[0] for row in names] == ["AZ Diest", "UZ Leuven"]
    database.close()


def test_the_practice_names_a_hospital_holds_become_practices(tmp_path: Path) -> None:
    """A demo volume holds samples by practice name; 0003 makes each name a
    practice, its slug the certificate name, and keeps every sample."""
    env = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "hospital.settings",
        "DATA_DIR": str(tmp_path),
        "DJANGO_DEBUG": "1",
    }

    def migrate_hospital(*target: str) -> None:
        subprocess.run(
            [sys.executable, str(ROOT / "manage.py"), "migrate", *target, "-v0"],
            env=env,
            check=True,
        )

    migrate_hospital("lab", "0002")
    database = sqlite3.connect(tmp_path / "web.sqlite3")
    with database:
        database.executemany(
            "INSERT INTO lab_sample (practice, sample_id) VALUES (?, ?)",
            [
                ("Huisartsenpraktijk De Ceder", "135318-1"),
                ("Huisartsenpraktijk De Ceder", "135318-2"),
                ("Huisartsenpraktijk De Berk", "135318-1"),
            ],
        )
    migrate_hospital("lab", "0003")
    practices = database.execute(
        "SELECT certificate_name, name FROM lab_practice ORDER BY name"
    ).fetchall()
    assert practices == [
        ("huisartsenpraktijk-de-berk", "Huisartsenpraktijk De Berk"),
        ("huisartsenpraktijk-de-ceder", "Huisartsenpraktijk De Ceder"),
    ]
    samples = database.execute(
        "SELECT certificate_name, sample_id FROM lab_sample"
        " JOIN lab_practice ON lab_practice.id = lab_sample.practice_id"
        " ORDER BY certificate_name, sample_id"
    ).fetchall()
    assert samples == [
        ("huisartsenpraktijk-de-berk", "135318-1"),
        ("huisartsenpraktijk-de-ceder", "135318-1"),
        ("huisartsenpraktijk-de-ceder", "135318-2"),
    ]
    database.close()


def test_a_general_practitioner_record_becomes_the_users_role(tmp_path: Path) -> None:
    """A demo volume holds the general practitioner as a record linked to a user;
    0007 makes it the user's role, and the one-per-practice constraint follows."""
    migrate(tmp_path, "practice", "0006")
    migrate(tmp_path, "accounts", "0002")
    database = sqlite3.connect(tmp_path / "web.sqlite3")
    with database:
        for username in ("doctor", "no-role"):
            database.execute(
                "INSERT INTO accounts_user (username, password, is_superuser,"
                " first_name, last_name, email, is_staff, is_active, date_joined)"
                " VALUES (?, '', 0, '', '', '', 0, 1, '2026-11-06')",
                (username,),
            )
        database.execute(
            "INSERT INTO practice_generalpractitioner (user_id, name)"
            " SELECT id, 'Dr. Demo' FROM accounts_user WHERE username = 'doctor'"
        )
    migrate(tmp_path)
    roles = database.execute(
        "SELECT username, role FROM accounts_user ORDER BY username"
    )
    assert roles.fetchall() == [("doctor", "general_practitioner"), ("no-role", None)]
    with pytest.raises(sqlite3.IntegrityError), database:
        database.execute("UPDATE accounts_user SET role = 'general_practitioner'")
    database.close()
