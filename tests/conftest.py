"""Test-wide settings, the scenarios' world, and what every party's tests and
the demo's share. Each party's builders are in tests/<party>/conftest.py."""

from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    import pandas as pd

    from web.accounts.models import User
    from web.accounts.roles import Role
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
    from web.accounts.models import User

    return User.objects.create_user(username=name.lower().replace(" ", "-"), role=role)


# (sex, age, ferritin) per group, in the order seeding.Group lists them.
PEOPLE = [
    ("Female", 30, 8.0),  # eligible, ferritin below 15
    ("Female", 25, 40.0),  # eligible, ferritin 15 or more
    ("Male", 35, None),  # men
    ("Female", 70, None),  # women outside 18-49
]
# Eligible women whom NHANES did not measure: never seeded.
UNMEASURED = ("Female", 40, None)


def nhanes_rows() -> "pd.DataFrame":
    """Four participants per group, so the seed has to choose."""
    import pandas as pd

    rows = [
        {
            "sample_id": 1000 + 10 * group + copy,
            "sex": sex,
            "age": age,
            **dict.fromkeys(CBC_VARS, float(group)),
            "LBXFER": ferritin,
        }
        for group, (sex, age, ferritin) in enumerate([*PEOPLE, UNMEASURED])
        for copy in range(4)
    ]
    return pd.DataFrame(rows)
