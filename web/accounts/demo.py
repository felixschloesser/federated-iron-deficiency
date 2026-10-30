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

from iron_deficiency.dataset import (
    ELIGIBLE_AGES,
    ELIGIBLE_SEX,
    FERRITIN_THRESHOLD,
    load_ferritin,
    load_new_samples,
)
from web.accounts.models import User

PASSWORD = "demo-pass-2026"
PER_GROUP = 3


class Group(enum.Enum):
    """Kinds of patient, so that every screening outcome can be shown."""

    LOW_FERRITIN = "eligible women with ferritin below the cutoff"
    NORMAL_FERRITIN = "eligible women with ferritin at or above the cutoff"
    NO_FERRITIN = "eligible women without ferritin in NHANES"
    MEN = "men"
    OUTSIDE_AGES = "women outside the eligible ages"

    def selects(self, rows: pd.DataFrame) -> "pd.Series[bool]":
        women = rows["sex"] == ELIGIBLE_SEX
        eligible = women & rows["age"].between(*ELIGIBLE_AGES)
        match self:
            case Group.LOW_FERRITIN:
                return eligible & (rows["LBXFER"] < FERRITIN_THRESHOLD)
            case Group.NORMAL_FERRITIN:
                return eligible & (rows["LBXFER"] >= FERRITIN_THRESHOLD)
            case Group.NO_FERRITIN:
                return eligible & rows["LBXFER"].isna()
            case Group.MEN:
                return ~women
            case Group.OUTSIDE_AGES:
                return women & ~rows["age"].between(*ELIGIBLE_AGES)
            case _:
                assert_never(self)


def load_nhanes() -> pd.DataFrame:
    """The 2021–2023 participants: sample ID, sex, age, 13 CBC values, ferritin."""
    return load_new_samples().merge(load_ferritin(), on="sample_id", how="left")


def choose(rows: pd.DataFrame, seed: int) -> pd.DataFrame:
    """PER_GROUP participants of each group, the same ones for the same seed."""
    return pd.concat(
        [
            rows[group.selects(rows)].sample(n=PER_GROUP, random_state=seed)
            for group in Group
        ]
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

    def seed(self, rows: list[dict[Hashable, Any]]) -> list[str]:
        """Create this party's accounts and records; return the usernames."""
        raise NotImplementedError

    def handle(self, *args: Any, **options: Any) -> None:
        if not settings.DEBUG:
            raise CommandError(
                "Demo accounts share a known password; run with DJANGO_DEBUG=1."
            )
        nhanes = pd.read_csv(options["nhanes"]) if options["nhanes"] else load_nhanes()
        rows = choose(nhanes, seed=options["seed"]).to_dict("records")
        with transaction.atomic():
            accounts = self.seed(rows)
            user("no-role")  # Has no role: for the refusal at login.
        self.stdout.write(
            f"Accounts {', '.join(accounts)} and no-role, password {PASSWORD};"
            f" {len(rows)} NHANES participants"
        )
