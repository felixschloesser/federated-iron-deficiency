"""Which NHANES participants the demo seeds, and their made-up parts.

Each party seeds the same participants for the same seed: the practice its
patients, the hospital what the analyser measures for them
(demo/seeding/parties.py)."""

import enum
from typing import assert_never

import pandas as pd

from ml.cohort import ELIGIBLE_SEX, eligible, iron_deficient
from ml.dataset import new_cycle_ferritin_and_crp, new_cycle_participants
from web.shared.vocabulary import RegisteredSex

# Patients per practice unless --patients says otherwise; the groups share them.
PATIENTS = 12


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


def load_nhanes() -> pd.DataFrame:
    """The 2021–2023 participants: sample ID, sex, age, 13 CBC values, ferritin
    and CRP."""
    return new_cycle_participants().merge(
        new_cycle_ferritin_and_crp(), on="sample_id", how="left"
    )


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


def with_made_up_ferritin(chosen: pd.DataFrame, nhanes: pd.DataFrame) -> pd.DataFrame:
    """Add a made-up ferritin for each chosen participant NHANES did not measure
    (it measured women aged 12–49 only): the measured ferritin of an eligible woman
    not iron deficient, picked by sample ID so it is the same on every seed."""
    measured = nhanes[Group.NOT_IRON_DEFICIENT.selects(nhanes)]
    pool = measured.sort_values("sample_id")["LBXFER"].to_list()
    made_up = chosen["sample_id"].map(lambda seqn: pool[int(seqn) % len(pool)])
    return chosen.assign(made_up_ferritin=made_up.where(chosen["LBXFER"].isna()))


# Fictional names that sound like Flanders: the ten most common family names of
# the Flemish Region on 1 January 2026 (Statbel, "Family names"), and common
# Flemish first names, led by Maria and Marc, the most common there (Statbel,
# "Maria, Marie, Monique, Martine…", 2018). Any real person sharing one is chance.
SURNAMES = (
    "Peeters",
    "Janssens",
    "Maes",
    "Jacobs",
    "Willems",
    "Mertens",
    "Claes",
    "Wouters",
    "Goossens",
    "De Smet",
)


def first_names(sex: RegisteredSex) -> tuple[str, ...]:
    match sex:
        case RegisteredSex.FEMALE:
            return (
                "Maria",
                "Sarah",
                "Laura",
                "Julie",
                "Lotte",
                "Emma",
                "Lien",
                "Sofie",
            )
        case RegisteredSex.MALE:
            return ("Marc", "Jan", "Luc", "Peter", "Tom", "Pieter", "Bart", "Wim")
        case _:
            assert_never(sex)


def patient_name(nhanes_number: int, sex: RegisteredSex) -> str:
    """A fictional name for a demo patient, the same on every seed."""
    first = first_names(sex)
    return (
        f"{first[nhanes_number % len(first)]}"
        f" {SURNAMES[nhanes_number // len(first) % len(SURNAMES)]}"
    )
