"""Test-wide settings, the scenarios' world, and what every party's tests and
the demo's share. Each party's builders are in tests/<party>/conftest.py."""

from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    import pandas as pd

    from web.shared.accounts.models import User
    from web.shared.accounts.roles import Role
from ml.cohort import CBC_VARS

# The compose project and what runs in it, for every test that needs Docker
# (tests/compose_project.py): one project per test run, whichever folder asks.
from tests.compose_project import (
    compose,
    compose_folder,
    engine_to_itself,
    flower,
    hospital_app,
    proxy,
    superlink,
)

# Fixtures defined there, offered to every test from here.
__all__ = [
    "compose",
    "compose_folder",
    "engine_to_itself",
    "flower",
    "hospital_app",
    "proxy",
    "superlink",
]

World = dict[str, Any]


@pytest.fixture
def world() -> World:
    """What the steps of one scenario have built so far, by name."""
    return {"general_practitioners": {}, "patients": {}}


def make_user(name: str, role: "Role") -> "User":
    from web.shared.accounts.models import User

    return User.objects.create_user(username=name.lower().replace(" ", "-"), role=role)


# (sex, age, ferritin) per group, in the order seeding.Group lists them; CRP 1.
PEOPLE = [
    ("Female", 30, 8.0),  # eligible, iron deficient
    ("Female", 25, 40.0),  # eligible, not iron deficient
    ("Male", 35, None),  # men
    ("Female", 70, None),  # women outside 18-49
]
# Eligible women whom NHANES did not measure: never seeded.
UNMEASURED = ("Female", 40, None)


def nhanes_rows() -> "pd.DataFrame":
    """Twenty participants per group, so the seed has to choose even a
    practice's stock of sample IDs (three for each of 12 patients: 36 of the 40
    eligible women with ferritin)."""
    import pandas as pd

    rows = [
        {
            "sample_id": 1000 + 100 * group + copy,
            "sex": sex,
            "age": age,
            **dict.fromkeys(CBC_VARS, float(group)),
            "LBXFER": ferritin,
            "CRP": None if ferritin is None else 1.0,
        }
        for group, (sex, age, ferritin) in enumerate([*PEOPLE, UNMEASURED])
        for copy in range(20)
    ]
    return pd.DataFrame(rows)


def write_extracts(folder: Path) -> tuple[Path, Path]:
    """nhanes-download's extracts (demo/nhanes.py's own extracts()) from
    nhanes_rows(), for one hospital and its practice of 12 patients; the
    hospital's folder and the practice's."""
    from demo.nhanes import Pair, extracts

    rows = nhanes_rows()
    records = rows.dropna(subset=["LBXFER"]).assign(pregnant=False)
    pair = Pair("2017-2018", "hospital", "practice", 12)
    for path, frame in extracts([pair], lambda _: records, rows).items():
        (folder / path).parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(folder / path, index=False)
    return folder / "hospital", folder / "practice"
