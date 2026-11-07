"""Which NHANES participants the demo seeds (demo/seeding/participants.py): the
iron-deficient group is iron deficient as the model learns it."""

import pandas as pd

from demo.seeding.participants import Group


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
