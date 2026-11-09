"""Which NHANES 2021–2023 participants the demo seeds.

Every hospital's analyser stand-in holds the same pool: women aged 18–49 with a
complete CBC and a measured ferritin, the people the screening is for. A
practice's stock of sample IDs is a seeded draw of the pool's numbers, so each
sample carries the blood of the participant its sample ID names. Its patients
are drawn apart, from every group, so every screening outcome can be shown."""

import enum
from typing import assert_never

import pandas as pd

from ml.cohort import ELIGIBLE_SEX, eligible, iron_deficient

# Patients per practice unless nhanes-download's --pair says otherwise; the
# groups share them.
PATIENTS = 12
# Sample IDs in a practice's stock for each of its patients.
SAMPLE_IDS_PER_PATIENT = 3


class Group(enum.Enum):
    """Kinds of patient, so that every screening outcome can be shown."""

    IRON_DEFICIENT = "eligible women iron deficient"
    NOT_IRON_DEFICIENT = "eligible women not iron deficient"
    MEN = "men"
    OUTSIDE_AGES = "women outside the eligible ages"

    def selects(self, rows: pd.DataFrame) -> "pd.Series[bool]":
        women = rows["sex"] == ELIGIBLE_SEX
        screened = eligible(rows["sex"], rows["age"])
        # As the model learns it; without both results her label is unknown.
        known = rows["LBXFER"].notna() & rows["CRP"].notna()
        deficient = iron_deficient(rows["LBXFER"], rows["CRP"])
        match self:
            case Group.IRON_DEFICIENT:
                return screened & known & deficient
            case Group.NOT_IRON_DEFICIENT:
                return screened & known & ~deficient
            case Group.MEN:
                return ~women
            case Group.OUTSIDE_AGES:
                return women & ~screened
            case _:
                assert_never(self)


def choose(rows: pd.DataFrame, seed: int, patients: int = PATIENTS) -> pd.DataFrame:
    """`patients` participants shared by the groups, the first groups rounding up,
    the same ones for the same seed."""
    groups = list(Group)
    return pd.concat(
        [
            rows[group.selects(rows)].sample(
                n=patients // len(groups) + (number < patients % len(groups)),
                random_state=seed,
            )
            for number, group in enumerate(groups)
        ]
    )


def pool(rows: pd.DataFrame) -> pd.DataFrame:
    """The participants every hospital's analyser stand-in holds."""
    return rows[eligible(rows["sex"], rows["age"]) & rows["LBXFER"].notna()]


def stock(rows: pd.DataFrame, seed: int, patients: int = PATIENTS) -> pd.DataFrame:
    """A practice's stock of sample IDs: SAMPLE_IDS_PER_PATIENT numbers of the
    pool for each patient, the same for the same seed, in the order drawn."""
    drawn = pool(rows).sample(n=patients * SAMPLE_IDS_PER_PATIENT, random_state=seed)
    return drawn[["sample_id"]]


def patients(rows: pd.DataFrame, seed: int, count: int = PATIENTS) -> pd.DataFrame:
    """A practice's patients: their NHANES number (for a name), sex and age."""
    chosen = choose(rows, seed, count)
    return chosen.rename(columns={"sample_id": "seqn"})[["seqn", "sex", "age"]]
