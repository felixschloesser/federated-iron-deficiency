"""Each party seeds from its own extract of the same draw (demo/nhanes.py): the
practice its stock of sample IDs, the hospital what their tubes would measure
(python -m demo.seed practice, hospital). Each seeds its own folder in a
process of its own, as the demo does; what each party seeds alone is in
tests/<party>/test_seeding.py."""

import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

import pytest

from tests.conftest import write_extracts

pytestmark = pytest.mark.subprocess

ROOT = Path(__file__).resolve().parents[2]


def seed(party: str, folder: Path, arguments: list[str]) -> None:
    env = {
        **{key: value for key, value in os.environ.items() if key != "DATA_DIR"},
        "DJANGO_SETTINGS_MODULE": f"web.{party}.settings",
        "DATA_DIR": str(folder),
        "DJANGO_DEBUG": "1",
    }
    manage = [sys.executable, str(ROOT / "manage.py")]
    subprocess.run([*manage, "migrate", "-v0"], env=env, check=True)
    subprocess.run(
        [sys.executable, "-m", "demo.seed", party, *arguments],
        env=env,
        check=True,
        cwd=ROOT,
        capture_output=True,
    )


def column(folder: Path, query: str) -> set[str]:
    with closing(sqlite3.connect(folder / "web.sqlite3")) as database:
        return {str(value) for (value,) in database.execute(query)}


def test_the_hospitals_analyser_holds_a_tube_for_every_sample_id_of_the_practice(
    tmp_path: Path,
) -> None:
    extracts_hospital, extracts_practice = write_extracts(tmp_path / "nhanes")
    hospital, practice = tmp_path / "hospital", tmp_path / "practice"
    seed(
        "hospital",
        hospital,
        ["--rows", str(extracts_hospital / "participants.csv")]
        + ["--lab-records", str(extracts_hospital / "lab-records.csv")],
    )
    seed("practice", practice, ["--rows", str(extracts_practice / "sample-ids.csv")])
    tubes = column(hospital, "SELECT seqn FROM analyser_participant")
    sample_ids = column(practice, "SELECT value FROM practice_sampleid")
    assert tubes
    assert sample_ids == tubes
