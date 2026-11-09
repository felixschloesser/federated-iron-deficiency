"""Which NHANES participants the demo seeds, and their made-up parts.

Each party seeds the same participants for the same seed: the practice its stock
of sample IDs (their numbers) and its patients (some of them), the hospital what
its analyser measures for each sample ID (demo/seeding/parties.py)."""

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


def stock(rows: pd.DataFrame, seed: int, patients: int = PATIENTS) -> pd.DataFrame:
    """A practice's stock of sample IDs: SAMPLE_IDS_PER_PATIENT participants for
    each patient, drawn as choose() draws, so they hold the `patients` participants
    choose() would give, marked `patient`: a patient's first sample usually
    carries their own participant's blood."""
    chosen = choose(rows, seed, patients * SAMPLE_IDS_PER_PATIENT)
    patient_ids = set(choose(rows, seed, patients)["sample_id"])
    return chosen.assign(patient=chosen["sample_id"].isin(patient_ids))


def with_made_up_ferritin(chosen: pd.DataFrame, nhanes: pd.DataFrame) -> pd.DataFrame:
    """Add a made-up ferritin for each chosen participant NHANES did not measure
    (it measured women aged 12–49 only): the measured ferritin of an eligible woman
    not iron deficient, picked by sample ID so it is the same on every seed."""
    measured = nhanes[Group.NOT_IRON_DEFICIENT.selects(nhanes)]
    pool = measured.sort_values("sample_id")["LBXFER"].to_list()
    made_up = chosen["sample_id"].map(lambda seqn: pool[int(seqn) % len(pool)])
    return chosen.assign(made_up_ferritin=made_up.where(chosen["LBXFER"].isna()))
