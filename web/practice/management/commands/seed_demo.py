"""Create demo accounts and NHANES patients for manual and browser checks."""

import enum
from collections.abc import Hashable, Mapping
from pathlib import Path
from typing import Any, assert_never

import pandas as pd
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction

from iron_deficiency.dataset import (
    CBC_VARS,
    FERRITIN_THRESHOLD,
    load_ferritin,
    load_new_samples,
)
from iron_deficiency.screening import ELIGIBLE_AGES, ELIGIBLE_SEX
from web.accounts.models import User
from web.deployment.models import LaboratoryDirector
from web.lab.models import LaboratoryStaffMember
from web.nhanes.models import Participant
from web.practice.models import GeneralPractitioner, Patient, RegisteredSex

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


def general_practitioner(username: str, name: str) -> GeneralPractitioner:
    practitioner, _ = GeneralPractitioner.objects.get_or_create(
        user=user(username), defaults={"name": name}
    )
    return practitioner


def patient(
    row: Mapping[Hashable, Any], name: str, owner: GeneralPractitioner
) -> Patient:
    ferritin = row["LBXFER"]
    participant, _ = Participant.objects.get_or_create(
        seqn=int(row["sample_id"]),
        defaults={
            "cbc": {var: float(row[var]) for var in CBC_VARS},
            "ferritin": None if pd.isna(ferritin) else float(ferritin),
        },
    )
    record, _ = Patient.objects.get_or_create(
        participant=participant,
        defaults={
            "general_practitioner": owner,
            "name": name,
            "registered_sex": RegisteredSex(str(row["sex"]).lower()),
            "age": int(row["age"]),
        },
    )
    return record


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--seed", type=int, default=0, help="other patients for each hospital"
        )
        parser.add_argument(
            "--nhanes", type=Path, help="a CSV of load_nhanes() instead of the network"
        )

    def handle(self, *args: Any, **options: Any) -> None:
        if not settings.DEBUG:
            raise CommandError(
                "Demo accounts share a known password; run with DJANGO_DEBUG=1."
            )
        nhanes = pd.read_csv(options["nhanes"]) if options["nhanes"] else load_nhanes()
        rows = choose(nhanes, seed=options["seed"])
        with transaction.atomic():
            practitioners = [
                general_practitioner("doctor-a", "Dr. Demo A"),
                general_practitioner("doctor-b", "Dr. Demo B"),
            ]
            LaboratoryStaffMember.objects.get_or_create(
                user=user("lab-1"), defaults={"name": "Laboratory Staff 1"}
            )
            LaboratoryDirector.objects.get_or_create(
                user=user("director-1"), defaults={"name": "Laboratory Director 1"}
            )
            user("no-role")  # Has no role: for the refusal at login.
            for number, row in enumerate(rows.to_dict("records"), start=1):
                owner = practitioners[(number - 1) % len(practitioners)]
                patient(row, f"Test Patient {number}", owner)
        self.stdout.write(
            f"Accounts doctor-a, doctor-b, lab-1, director-1 and no-role, password {PASSWORD};"
            f" {len(rows)} NHANES patients"
        )
