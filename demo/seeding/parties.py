"""What each party's web app gets for the demo: its accounts, and its records of
the chosen NHANES participants. Runs inside that party's Django
(python -m demo.seed); the accounts share a known password."""

from collections.abc import Hashable
from pathlib import Path
from typing import Any

import pandas as pd
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
from demo.seeding.participants import patient_name
from ml.cohort import CBC_VARS
from web.shared.accounts.models import User
from web.shared.accounts.roles import Role
from web.shared.vocabulary import ClinicalIndication, RegisteredSex

Rows = list[dict[Hashable, Any]]


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
        ferritin, made_up = row["LBXFER"], row["made_up_ferritin"]
        Participant.objects.get_or_create(
            seqn=int(row["sample_id"]),
            defaults={
                "cbc": {var: float(row[var]) for var in CBC_VARS},
                "ferritin": None if pd.isna(ferritin) else float(ferritin),
                "made_up_ferritin": None if pd.isna(made_up) else float(made_up),
            },
        )
    user("no-role", None)  # Has no role: for the refusal at login.
    return [LABORATORY_STAFF, LABORATORY_DIRECTOR]


@transaction.atomic
def seed_practice(rows: Rows) -> list[str]:
    """The practice's general practitioner, and a patient for each chosen
    participant, whose samples start with its number."""
    from web.practice.models import Patient

    user(GENERAL_PRACTITIONER, Role.GENERAL_PRACTITIONER)
    for row in rows:
        seqn = int(row["sample_id"])
        sex = RegisteredSex.of_nhanes(str(row["sex"]))
        Patient.objects.get_or_create(
            nhanes_number=str(seqn),
            defaults={
                "name": patient_name(seqn, sex),
                "registered_sex": sex,
                "age": int(row["age"]),
            },
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
    screened = ClinicalIndication.screened()
    return screened[number % len(screened)]


def seed_lab_records(csv: Path, provide: bool) -> str:
    """The hospital's lab records (DS1), once, from a CSV prepare wrote
    (ml.dataset.participants); with `provide`, the laboratory director then
    provides the training cohort, as on the Training cohort page."""
    from web.hospital.cohort.models import LabRecord, TrainingCohort

    with transaction.atomic():
        if not LabRecord.objects.exists():
            LabRecord.objects.bulk_create(
                LabRecord(
                    registered_sex=RegisteredSex.of_nhanes(str(row["sex"])),
                    age=int(row["age"]),
                    cbc={
                        var: float(row[var])
                        for var in CBC_VARS
                        if not pd.isna(row[var])
                    },
                    ferritin=None if pd.isna(row["LBXFER"]) else float(row["LBXFER"]),
                    crp=None if pd.isna(row["CRP"]) else float(row["CRP"]),
                    clinical_indication=indication(bool(row["pregnant"]), number),
                )
                for number, row in enumerate(pd.read_csv(csv).to_dict("records"))
            )
    summary = f"{LabRecord.objects.count()} lab records"
    if not provide:
        return summary
    director = User.objects.filter(role=Role.LABORATORY_DIRECTOR).first()
    if director is None or settings.TRAINING_COHORT_DIR is None:
        raise SystemExit(
            "Providing needs the laboratory director (python -m demo.seed hospital)"
            " and TRAINING_COHORT_DIR."
        )
    try:
        TrainingCohort.objects.provide(
            directory=settings.TRAINING_COHORT_DIR, by=director, now=timezone.now()
        )
    except ValidationError as error:
        # Provided on an earlier run of prepare: nothing to do.
        if [refusal.code for refusal in error.error_list] != ["unchanged"]:
            raise SystemExit(" ".join(error.messages)) from error
    return f"{summary}; training cohort provided"
