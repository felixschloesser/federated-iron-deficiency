"""Demo seeding both parties share: accounts, and which NHANES participants.

Each party seeds the same participants for the same seed: the practice its
patients (seed_practice), the hospital what their tubes would measure
(seed_hospital)."""

import enum
from collections.abc import Hashable
from pathlib import Path
from typing import Any, assert_never

import pandas as pd
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction

from iron_deficiency.cohort import ELIGIBLE_SEX, FERRITIN_THRESHOLD, eligible
from iron_deficiency.dataset import load_ferritin, load_new_samples
from web.accounts.models import User
from web.seeding.accounts import PASSWORD
from web.vocabulary import RegisteredSex

# Patients per practice unless --patients says otherwise; the groups share them.
PATIENTS = 12


class Group(enum.Enum):
    """Kinds of patient, so that every screening outcome can be shown."""

    LOW_FERRITIN = "eligible women with ferritin below the cutoff"
    NORMAL_FERRITIN = "eligible women with ferritin at or above the cutoff"
    MEN = "men"
    OUTSIDE_AGES = "women outside the eligible ages"

    def selects(self, rows: pd.DataFrame) -> "pd.Series[bool]":
        women = rows["sex"] == ELIGIBLE_SEX
        screened = eligible(rows["sex"], rows["age"])
        match self:
            case Group.LOW_FERRITIN:
                return screened & (rows["LBXFER"] < FERRITIN_THRESHOLD)
            case Group.NORMAL_FERRITIN:
                return screened & (rows["LBXFER"] >= FERRITIN_THRESHOLD)
            case Group.MEN:
                return ~women
            case Group.OUTSIDE_AGES:
                return women & ~screened
            case _:
                assert_never(self)


def load_nhanes() -> pd.DataFrame:
    """The 2021–2023 participants: sample ID, sex, age, 13 CBC values, ferritin."""
    return load_new_samples().merge(load_ferritin(), on="sample_id", how="left")


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
    at or above the cutoff, picked by sample ID so it is the same on every seed."""
    measured = nhanes[
        eligible(nhanes["sex"], nhanes["age"])
        & (nhanes["LBXFER"] >= FERRITIN_THRESHOLD)
    ]
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


def user(username: str) -> User:
    account, created = User.objects.get_or_create(username=username)
    if created:
        account.set_password(PASSWORD)
        account.save()
    return account


class SeedCommand(BaseCommand):
    """Seeds one party's records for the chosen participants; `seed` says which."""

    help = __doc__

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--seed", type=int, default=0, help="other patients for each hospital"
        )
        parser.add_argument(
            "--nhanes", type=Path, help="a CSV of load_nhanes() instead of the network"
        )
        parser.add_argument(
            "--patients",
            type=int,
            default=PATIENTS,
            help="how many participants; the practice and its hospital need the same",
        )

    def seed(self, rows: list[dict[Hashable, Any]]) -> list[str]:
        """Create this party's accounts and records; return the usernames."""
        raise NotImplementedError

    def handle(self, *args: Any, **options: Any) -> None:
        if not settings.DEBUG:
            raise CommandError(
                "Demo accounts share a known password; run with DJANGO_DEBUG=1."
            )
        nhanes = pd.read_csv(options["nhanes"]) if options["nhanes"] else load_nhanes()
        chosen = choose(nhanes, seed=options["seed"], patients=options["patients"])
        rows = with_made_up_ferritin(chosen, nhanes).to_dict("records")
        with transaction.atomic():
            accounts = self.seed(rows)
            user("no-role")  # Has no role: for the refusal at login.
        self.stdout.write(
            f"Accounts {', '.join(accounts)} and no-role, password {PASSWORD};"
            f" {len(rows)} NHANES participants"
        )
