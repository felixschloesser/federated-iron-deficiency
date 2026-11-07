"""Each party seeds the same NHANES participants for the same seed: the practice
its patients, the hospital what their tubes would measure (seed_practice,
seed_hospital). Each seeds its own folder in a process of its own, as the demo
does; what each party seeds alone is in tests/<party>/test_seeding.py."""

import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

import pytest

from tests.conftest import nhanes_rows

pytestmark = pytest.mark.subprocess

ROOT = Path(__file__).resolve().parents[2]


def seed(party: str, folder: Path, nhanes: Path, seed_value: str) -> None:
    env = {
        **{key: value for key, value in os.environ.items() if key != "DATA_DIR"},
        "DJANGO_SETTINGS_MODULE": f"{party}.settings",
        "DATA_DIR": str(folder),
        "DJANGO_DEBUG": "1",
    }
    manage = [sys.executable, str(ROOT / "manage.py")]
    subprocess.run([*manage, "migrate", "-v0"], env=env, check=True)
    subprocess.run(
        [*manage, f"seed_{party}", "--nhanes", str(nhanes), "--seed", seed_value],
        env=env,
        check=True,
        capture_output=True,
    )


def column(folder: Path, query: str) -> set[str]:
    with closing(sqlite3.connect(folder / "shared.sqlite3")) as database:
        return {str(value) for (value,) in database.execute(query)}


@pytest.mark.parametrize("seed_value", ["0", "1"])
def test_the_practice_and_the_hospital_seed_the_same_participants(
    tmp_path: Path, seed_value: str
) -> None:
    nhanes = tmp_path / "nhanes.csv"
    nhanes_rows().to_csv(nhanes, index=False)
    hospital, practice = tmp_path / "hospital", tmp_path / "practice"
    seed("hospital", hospital, nhanes, seed_value)
    seed("practice", practice, nhanes, seed_value)
    tubes = column(hospital, "SELECT seqn FROM analyser_participant")
    patients = column(practice, "SELECT nhanes_number FROM practice_patient")
    assert tubes
    assert patients == tubes
