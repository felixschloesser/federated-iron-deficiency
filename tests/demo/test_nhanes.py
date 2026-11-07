"""nhanes-download's extracts (demo/nhanes.py): one folder per party, holding
only that party's part, written once."""

from pathlib import Path

import pandas as pd
import pytest

import ml.dataset
from demo import nhanes
from demo.topology import HOSPITALS, PATIENTS, PRACTICES, hospital_slug, nhanes_pairs
from ml.cohort import CBC_VARS
from ml.dataset import CYCLES

PEOPLE = [
    ("Female", 30, 8.0),
    ("Female", 25, 40.0),
    ("Male", 35, None),
    ("Female", 70, None),
]


def participants_2021_2023() -> pd.DataFrame:
    """Enough of each kind of patient for the largest practice to choose from."""
    return pd.DataFrame(
        [
            {
                "sample_id": 1000 + 100 * group + copy,
                "sex": sex,
                "age": age,
                **dict.fromkeys(CBC_VARS, float(group)),
                "LBXFER": ferritin,
                "CRP": None if ferritin is None else 1.0,
            }
            for group, (sex, age, ferritin) in enumerate(PEOPLE)
            for copy in range(20)
        ]
    )


# The demo's pairs, as compose passes them (demo/topology.py).
PAIRS = [
    nhanes.Pair(
        cycle,
        hospital_slug(HOSPITALS[cycle]),
        hospital_slug(PRACTICES[cycle]),
        PATIENTS[cycle],
    )
    for cycle in CYCLES
]


def test_compose_passes_every_pair() -> None:
    arguments = [part.strip().strip('"') for part in nhanes_pairs().split(",")]
    pairs = [arguments[index + 1 : index + 5] for index in range(0, len(arguments), 5)]
    assert [nhanes.Pair(c, h, p, int(n)) for c, h, p, n in pairs] == PAIRS


def lab_records(cycle: str) -> pd.DataFrame:
    return pd.DataFrame({"cycle": [cycle]})


def test_each_party_gets_only_its_own_extracts() -> None:
    files = nhanes.extracts(PAIRS, lab_records, participants_2021_2023())
    assert sorted(files) == sorted(nhanes.expected(PAIRS))
    patients = {}
    for cycle in CYCLES:
        hospital = hospital_slug(HOSPITALS[cycle])
        practice = hospital_slug(PRACTICES[cycle])
        assert {path.name for path in files if path.parent.name == hospital} == {
            "lab-records.csv",
            "participants.csv",
        }
        assert {path.name for path in files if path.parent.name == practice} == {
            "patients.csv"
        }
        assert files[Path(hospital, "lab-records.csv")]["cycle"].tolist() == [cycle]
        patients[practice] = files[Path(practice, "patients.csv")]
        assert len(patients[practice]) == PATIENTS[cycle]
    # Each hospital's analyser holds a tube for every practice's patients.
    every = set().union(*(set(rows["sample_id"]) for rows in patients.values()))
    for cycle in CYCLES:
        held = files[Path(hospital_slug(HOSPITALS[cycle]), "participants.csv")]
        assert set(held["sample_id"]) == every


def test_extracts_made_by_the_same_code_are_kept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ml.dataset, "participants", lab_records)
    monkeypatch.setattr(nhanes, "nhanes_2021_2023", participants_2021_2023)
    assert nhanes.download(tmp_path, PAIRS) is True
    assert all((tmp_path / path).is_file() for path in nhanes.expected(PAIRS))

    def offline(*_: object) -> pd.DataFrame:
        raise AssertionError("downloaded again")

    monkeypatch.setattr(ml.dataset, "participants", offline)
    monkeypatch.setattr(nhanes, "nhanes_2021_2023", offline)
    assert nhanes.download(tmp_path, PAIRS) is False
    # A missing extract, or other code, makes them again.
    monkeypatch.setattr(ml.dataset, "participants", lab_records)
    monkeypatch.setattr(nhanes, "nhanes_2021_2023", participants_2021_2023)
    (tmp_path / nhanes.expected(PAIRS)[0]).unlink()
    assert nhanes.download(tmp_path, PAIRS) is True
    (tmp_path / nhanes.FINGERPRINT).write_text("older code")
    assert nhanes.download(tmp_path, PAIRS) is True
    assert not list(tmp_path.rglob("*.partial"))
