"""Who the cohort holds and what the model reads: names only, no third-party
imports, so a web app can use them without the training data libraries."""

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
FERRITIN_CUTOFF = 15.0
# Who is screened: women of reproductive age (features/screening.feature).
ELIGIBLE_SEX = "Female"
ELIGIBLE_AGES = (18, 49)


def eligible(sex: "pd.Series", age: "pd.Series") -> "pd.Series[bool]":
    """Who is screened, and whom the model is trained on: women aged 18–49 (features/screening.feature).
    `sex` holds NHANES's labels."""
    return (sex == ELIGIBLE_SEX) & age.between(*ELIGIBLE_AGES)
