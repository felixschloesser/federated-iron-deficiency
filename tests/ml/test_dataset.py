"""The simulation's cohort holds whom the hospital's training cohort holds
(ml/dataset.py)."""

import pandas as pd

from ml.cohort import FEATURES
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
        }
        | {var: [1.0] * 3 for var in FEATURES if var != "RIDAGEYR"}
    )
    assert in_cohort(participants).tolist() == [False, True, True]
