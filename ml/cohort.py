"""Who belongs in the training cohort, and which values the model reads.

Both the training code and the hospital's web app import this, so a change here
changes both. It imports nothing outside the standard library at run time, so a
web app can use it without the training libraries installed."""

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
# WHO's definition of iron deficiency in adults (WHO ferritin guideline 2020,
# recommendations 1.1 and 1.2): ferritin below 15 ng/mL, or below 70 ng/mL when
# there is inflammation, meaning CRP above 5 mg/L.
FERRITIN_CUTOFF = 15.0
INFLAMED_FERRITIN_CUTOFF = 70.0
INFLAMMATION_CRP = 5.0
# Who is screened: women of reproductive age.
ELIGIBLE_SEX = "Female"
ELIGIBLE_AGES = (18, 49)


def eligible(sex: "pd.Series", age: "pd.Series") -> "pd.Series[bool]":
    """True for women aged 18–49: the people who are screened and whom the model
    trains on. `sex` uses NHANES's labels."""
    return (sex == ELIGIBLE_SEX) & age.between(*ELIGIBLE_AGES)


def iron_deficient(ferritin: "pd.Series", crp: "pd.Series") -> "pd.Series[bool]":
    """The training label: ferritin below 15 ng/mL, or below 70 ng/mL with
    inflammation."""
    return (ferritin < FERRITIN_CUTOFF) | (
        (crp > INFLAMMATION_CRP) & (ferritin < INFLAMED_FERRITIN_CUTOFF)
    )
