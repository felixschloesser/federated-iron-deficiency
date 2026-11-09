"""Which NHANES participants the demo seeds (demo/seeding/participants.py): the
iron-deficient group is iron deficient as the model learns it."""

import pandas as pd

from demo.seeding.participants import (
    SAMPLE_IDS_PER_PATIENT,
    Group,
    choose,
    pool,
    stock,
)
from tests.conftest import nhanes_rows


def test_an_inflamed_woman_with_ferritin_40_is_seeded_as_iron_deficient() -> None:
    """WHO's rule (ml.cohort.iron_deficient): below 70 ng/mL with CRP above 5."""
    rows = pd.DataFrame(
        {
            "sex": ["Female"] * 3,
            "age": [30] * 3,
            "LBXFER": [40.0] * 3,
            "CRP": [12.0, 1.0, None],
        }
    )
    assert Group.IRON_DEFICIENT.selects(rows).tolist() == [True, False, False]
    # Without a CRP her label is unknown: she is in neither group.
    assert Group.NOT_IRON_DEFICIENT.selects(rows).tolist() == [False, True, False]


def test_each_seed_chooses_other_participants() -> None:
    rows = nhanes_rows()
    assert not choose(rows, seed=0).equals(choose(rows, seed=1))


def test_the_number_of_patients_is_shared_by_the_groups() -> None:
    """The first groups round up: 2, 2, 1, 1 of 6."""
    chosen = choose(nhanes_rows(), seed=0, patients=6)
    assert chosen["age"].value_counts().to_dict() == {30: 2, 25: 2, 35: 1, 70: 1}


def test_a_stock_holds_three_sample_ids_of_the_pool_for_each_patient() -> None:
    rows = nhanes_rows()
    drawn = stock(rows, seed=0, patients=6)
    assert len(drawn) == SAMPLE_IDS_PER_PATIENT * 6
    assert set(drawn["sample_id"]) <= set(pool(rows)["sample_id"])


def test_the_pool_is_the_eligible_women_with_ferritin() -> None:
    assert set(pool(nhanes_rows())["age"]) == {30, 25}
