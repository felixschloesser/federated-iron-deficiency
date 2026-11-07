"""The simulation's cohort holds whom the hospital's training cohort holds
(ml/dataset.py)."""

import pandas as pd

from ml.cohort import FEATURES, iron_deficient
from ml.dataset import in_cohort


def test_a_woman_pregnant_at_the_exam_is_not_in_the_cohort() -> None:
    """As a CBC ordered at the start of pregnancy is not in a hospital's
    (features/hospital/training_cohort.feature)."""
    participants = pd.DataFrame(
        {
            "RIAGENDR": ["Female"] * 3,
            "RIDAGEYR": [30.0] * 3,
            "RIDEXPRG": [
                "Yes, positive lab pregnancy test or self-reported pregnant at exam",
                "The participant was not pregnant at exam",
                None,
            ],
            "LBXFER": [20.0] * 3,
            "CRP": [1.0] * 3,
        }
        | {var: [1.0] * 3 for var in FEATURES if var != "RIDAGEYR"}
    )
    assert in_cohort(participants).tolist() == [False, True, True]


def test_a_woman_without_a_crp_is_not_in_the_cohort() -> None:
    """As a past patient without a CRP result is not in a hospital's."""
    participants = pd.DataFrame(
        {
            "RIAGENDR": ["Female"] * 2,
            "RIDAGEYR": [30.0] * 2,
            "RIDEXPRG": [None] * 2,
            "LBXFER": [20.0] * 2,
            "CRP": [1.0, None],
        }
        | {var: [1.0] * 2 for var in FEATURES if var != "RIDAGEYR"}
    )
    assert in_cohort(participants).tolist() == [True, False]


def test_with_inflammation_ferritin_below_70_is_iron_deficient() -> None:
    """WHO's cutoffs for adults: 15 ng/mL, 70 with CRP above 5 mg/L."""
    ferritin = pd.Series([14.0, 15.0, 40.0, 40.0, 69.0, 70.0])
    crp = pd.Series([1.0, 1.0, 5.0, 5.1, 12.0, 12.0])
    assert iron_deficient(ferritin, crp).tolist() == [
        True,
        False,
        False,
        True,
        True,
        False,
    ]
