"""nhanes-download's extracts (demo/nhanes.py): one folder per party, holding
only that party's part, written once."""

from pathlib import Path

import pandas as pd
import pytest

import ml.dataset
from demo import nhanes
from demo.seeding.participants import SAMPLE_IDS_PER_PATIENT
from ml.cohort import CBC_VARS

PEOPLE = [
    ("Female", 30, 8.0),
    ("Female", 25, 40.0),
    ("Male", 35, None),
    ("Female", 70, None),
]


def participants_2021_2023() -> pd.DataFrame:
    """Enough of each kind of patient for the largest practice: 40 patients and a
    stock of 120 sample IDs from the pool's 140 eligible women."""
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
            for copy in range(70)
        ]
    )


# Pairs as compose passes them (demo/compose.yaml checks its own, in
# tests/quality/security/test_compose.py).
PAIRS = [
    nhanes.Pair("2005-2006", "uz-leuven", "huisartsenpraktijk-de-akker", 40),
    nhanes.Pair("2015-2016", "heilig-hart-leuven", "huisartsenpraktijk-de-berk", 24),
    nhanes.Pair("2017-2018", "az-diest", "huisartsenpraktijk-de-ceder", 12),
]


def lab_records(cycle: str) -> pd.DataFrame:
    return pd.DataFrame({"cycle": [cycle]})


def test_each_party_gets_only_its_own_extracts() -> None:
    files = nhanes.extracts(PAIRS, lab_records, participants_2021_2023())
    assert sorted(files) == sorted(nhanes.expected(PAIRS))
    stocks = {}
    for pair in PAIRS:
        hospital, practice, cycle = pair.hospital, pair.practice, pair.cycle
        assert {path.name for path in files if path.parent.name == hospital} == {
            "lab-records.csv",
            "participants.csv",
        }
        assert {path.name for path in files if path.parent.name == practice} == {
            "sample-ids.csv",
            "patients.csv",
        }
        assert files[Path(hospital, "lab-records.csv")]["cycle"].tolist() == [cycle]
        stock = files[Path(practice, "sample-ids.csv")]
        # No blood values reach the practice.
        assert list(stock.columns) == ["sample_id"]
        assert len(stock) == SAMPLE_IDS_PER_PATIENT * pair.patients
        assert list(files[Path(practice, "patients.csv")].columns) == [
            "seqn",
            "sex",
            "age",
        ]
        assert len(files[Path(practice, "patients.csv")]) == pair.patients
        stocks[practice] = stock
    # Each hospital's analyser holds a tube for every practice's sample IDs.
    every = set().union(*(set(rows["sample_id"]) for rows in stocks.values()))
    for pair in PAIRS:
        held = files[Path(pair.hospital, "participants.csv")]
        assert every <= set(held["sample_id"])


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
