"""A party's web container's start (demo/party.py): it sets itself up from its
own environment and its own NHANES extract."""

import re
from pathlib import Path

import pytest

from demo.party import NHANES, registrations, seeding

ROOT = Path(__file__).resolve().parents[2]

# What each party's folder may hold: the report's DFD stores, and the Django
# secret key its web app uses (demo/README.md).
PARTY_FOLDERS = {
    "startup": {
        "superlink",  # the SuperLink's own state, no DFD store
        "final-models",  # DS4
        "flwr-home",
        "web.sqlite3",  # the data scientist's account
        ".secret_key",
    },
    "hospital": {
        "cohort",  # DS2
        "screening-models",  # DS5
        "web.sqlite3",  # DS1, DS6, DS8, DS9
        ".secret_key",
    },
    "practice": {"web.sqlite3", ".secret_key"},  # DS7
}


@pytest.mark.parametrize("party", sorted(PARTY_FOLDERS))
def test_each_image_brings_only_its_partys_dfd_stores(party: str) -> None:
    """Docker copies the folders a party's image makes under /data into its fresh
    volume: only the party's own stores."""
    dockerfile = (ROOT / "demo" / f"{party}.Dockerfile").read_text()
    made = " ".join(re.findall(r"^RUN mkdir -p (.+)$", dockerfile, re.MULTILINE))
    folders = {path.removeprefix("/data/") for path in made.split()}
    assert folders <= PARTY_FOLDERS[party]


@pytest.mark.parametrize("party", ["hospital", "practice", "startup"])
def test_a_party_seeds_only_from_its_own_extract(party: str) -> None:
    for command in seeding(party, {}):
        paths = [Path(part) for part in command if part.startswith("/")]
        assert all(path.parent == NHANES for path in paths), command


def test_a_hospital_provides_its_training_cohort_only_when_told() -> None:
    assert "--provide" not in seeding("hospital", {})[1]
    assert "--provide" in seeding("hospital", {"DEMO_PROVIDE": "1"})[1]


def test_a_party_registers_only_whom_it_knows() -> None:
    lines = "add_practice de-ceder 'Huisartsenpraktijk De Ceder'\n\n"
    assert registrations(lines) == [
        ["add_practice", "de-ceder", "Huisartsenpraktijk De Ceder"]
    ]
    with pytest.raises(SystemExit):
        registrations("flush --no-input\n")


def _database(folder: Path, migrations: list[tuple[str, str]]) -> Path:
    import sqlite3

    path = folder / "web.sqlite3"
    database = sqlite3.connect(path)
    with database:
        database.execute("CREATE TABLE django_migrations (app TEXT, name TEXT)")
        database.executemany("INSERT INTO django_migrations VALUES (?, ?)", migrations)
    database.close()
    return path


def test_a_database_from_before_a_migration_reset_is_set_aside(tmp_path: Path) -> None:
    """A demo volume's database that records migrations the code no longer has
    cannot migrate: its web app renames it aside, keeping it, and starts afresh."""
    from demo.party import set_aside_stale_database

    path = _database(tmp_path, [("lab", "0001_initial"), ("lab", "0002_gone")])
    assert set_aside_stale_database(tmp_path) == tmp_path / "web.sqlite3.before-reset"
    assert not path.exists()
    assert (tmp_path / "web.sqlite3.before-reset").exists()


def test_a_current_database_is_kept(tmp_path: Path) -> None:
    from demo.party import set_aside_stale_database

    path = _database(tmp_path, [("lab", "0001_initial"), ("admin", "0001_initial")])
    assert set_aside_stale_database(tmp_path) is None
    assert path.exists()
    assert set_aside_stale_database(tmp_path / "none") is None
