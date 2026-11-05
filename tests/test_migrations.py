"""Migrations on databases the demo already holds."""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def migrate(practice: Path, *target: str) -> None:
    env = {**os.environ, "PRACTICE_DIR": str(practice), "DJANGO_DEBUG": "1"}
    env.pop("DATABASE_NAME", None)
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
