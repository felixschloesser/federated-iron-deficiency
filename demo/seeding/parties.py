"""What each party's web app gets for the demo: its accounts, and its records of
the chosen NHANES participants. Runs inside that party's Django
(python -m demo.seed); the accounts share a known password."""

import csv
import math
from collections.abc import Hashable
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from demo.seeding.accounts import (
    DATA_SCIENTIST,
    GENERAL_PRACTITIONER,
    LABORATORY_DIRECTOR,
    LABORATORY_STAFF,
    PASSWORD,
)
from demo.seeding.names import patient_name
from ml.cohort import CBC_VARS
from web.shared.accounts.models import User
from web.shared.accounts.roles import Role
from web.shared.vocabulary import ClinicalIndication, RegisteredSex

Rows = list[dict[Hashable, Any]]


def measured(value: object) -> float | None:
    """A value from a CSV or a table: None where it is blank or not a number."""
    if value is None or value == "":
        return None
    number = float(str(value))
    return None if math.isnan(number) else number


def read_rows(path: Path) -> Rows:
    with path.open(newline="") as file:
        return list(csv.DictReader(file))


def user(username: str, role: Role | None) -> User:
    account, created = User.objects.get_or_create(
        username=username, defaults={"role": role}
    )
    if created:
        account.set_password(PASSWORD)
        account.save()
    return account


@transaction.atomic
def seed_hospital(rows: Rows) -> list[str]:
    """The hospital's laboratory staff and director, and what its analyser's
    stand-in measures for each chosen participant."""
    from web.hospital.analyser.models import Participant

    user(LABORATORY_STAFF, Role.LABORATORY_STAFF)
    user(LABORATORY_DIRECTOR, Role.LABORATORY_DIRECTOR)
    for row in rows:
        Participant.objects.get_or_create(
            seqn=int(row["sample_id"]),
            defaults={
                "cbc": {var: float(row[var]) for var in CBC_VARS},
                "ferritin": float(row["LBXFER"]),
            },
        )
    user("no-role", None)  # Has no role: for the refusal at login.
    return [LABORATORY_STAFF, LABORATORY_DIRECTOR]


@transaction.atomic
def seed_practice(sample_ids: Rows, patients: Rows) -> list[str]:
    """The practice's general practitioner, its stock of sample IDs in the order
    drawn, and, once, its patients, each named after their NHANES number."""
    from web.practice.models import Patient, SampleId

    user(GENERAL_PRACTITIONER, Role.GENERAL_PRACTITIONER)
    for row in sample_ids:
        SampleId.objects.get_or_create(value=str(int(row["sample_id"])))
    if not Patient.objects.exists():
        for row in patients:
            sex = RegisteredSex.of_nhanes(str(row["sex"]))
            Patient.objects.create(
                name=patient_name(int(row["seqn"]), sex),
                registered_sex=sex,
                age=int(float(row["age"])),
            )
    user("no-role", None)
    return [GENERAL_PRACTITIONER]


@transaction.atomic
def seed_startup() -> list[str]:
    """The startup's data scientist; the startup holds no patients."""
    user(DATA_SCIENTIST, Role.DATA_SCIENTIST)
    user("no-role", None)
    return [DATA_SCIENTIST]


def indication(pregnant: bool, number: int) -> ClinicalIndication:
    """A past CBC's indication: at the start of pregnancy for a woman NHANES
    found pregnant, else one of the screened indications in turn."""
    if pregnant:
        return ClinicalIndication.START_OF_PREGNANCY
    from web.hospital.lab.models import SCREENED_INDICATIONS

    return SCREENED_INDICATIONS[number % len(SCREENED_INDICATIONS)]


def seed_lab_records(csv_path: Path, provide: bool) -> str:
    """The hospital's lab records (DS1), once, from nhanes-download's CSV
    (demo/nhanes.py); with `provide`, the laboratory director then
    provides the training cohort, as on the Training cohort page."""
    from web.hospital.cohort.models import LabRecord, TrainingCohort

    with transaction.atomic():
        if not LabRecord.objects.exists():
            LabRecord.objects.bulk_create(
                LabRecord(
                    registered_sex=RegisteredSex.of_nhanes(str(row["sex"])),
                    age=int(float(row["age"])),
                    cbc={
                        var: value
                        for var in CBC_VARS
                        if (value := measured(row[var])) is not None
                    },
                    ferritin=measured(row["LBXFER"]),
                    crp=measured(row["CRP"]),
                    clinical_indication=indication(
                        str(row["pregnant"]) == "True", number
                    ),
                )
                for number, row in enumerate(read_rows(csv_path))
            )
    summary = f"{LabRecord.objects.count()} lab records"
    if not provide:
        return summary
    director = User.objects.filter(role=Role.LABORATORY_DIRECTOR).first()
    if director is None:
        raise SystemExit("Providing needs the laboratory director (seeded first).")
    try:
        TrainingCohort.objects.provide(
            directory=settings.TRAINING_COHORT_DIR, by=director, now=timezone.now()
        )
    except ValidationError as error:
        # Provided on an earlier start: nothing to do.
        if [refusal.code for refusal in error.error_list] != ["unchanged"]:
            raise SystemExit(" ".join(error.messages)) from error
    return f"{summary}; training cohort provided"
