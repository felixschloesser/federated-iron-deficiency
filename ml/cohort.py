"""Who the cohort holds and what the model reads: the kernel the training code
and the hospital share. Names only, no third-party imports, so a web app can use
them without the training data libraries. A change here changes both: the
hospital's scenarios and the training code's."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd

CBC_VARS = [
    "LBXWBCSI",
    "LBXRBCSI",
    "LBXHGB",
    "LBXHCT",
    "LBXMCVSI",
    "LBXMC",
    "LBXMCHSI",
    "LBXRDW",
    "LBXPLTSI",
    "LBXMPSI",
    "LBDLYMNO",
    "LBDNENO",
    "LBDMONO",
]
FEATURES = CBC_VARS + ["RIDAGEYR"]
# Iron deficiency in adults (WHO, ferritin guideline, 2020, recommendations 1.1
# and 1.2): ferritin below 15 ng/mL, or below 70 ng/mL with inflammation,
# which is CRP above 5 mg/L.
FERRITIN_CUTOFF = 15.0
INFLAMED_FERRITIN_CUTOFF = 70.0
INFLAMMATION_CRP = 5.0
# Who is screened: women of reproductive age.
ELIGIBLE_SEX = "Female"
ELIGIBLE_AGES = (18, 49)


def eligible(sex: "pd.Series", age: "pd.Series") -> "pd.Series[bool]":
    """Who is screened, and whom the model is trained on: women aged 18–49.
    `sex` holds NHANES's labels."""
    return (sex == ELIGIBLE_SEX) & age.between(*ELIGIBLE_AGES)


def iron_deficient(ferritin: "pd.Series", crp: "pd.Series") -> "pd.Series[bool]":
    """The label: ferritin below 15 ng/mL, or below 70 ng/mL with inflammation."""
    return (ferritin < FERRITIN_CUTOFF) | (
        (crp > INFLAMMATION_CRP) & (ferritin < INFLAMED_FERRITIN_CUTOFF)
    )
