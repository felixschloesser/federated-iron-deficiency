"""Create the practice's demo general practitioners and their NHANES patients."""

from collections.abc import Hashable
from typing import Any

from web.practice.models import GeneralPractitioner, Patient
from web.seeding.accounts import GENERAL_PRACTITIONER, GENERAL_PRACTITIONER_NAME
from web.seeding.command import SeedCommand, patient_name, user
from web.vocabulary import RegisteredSex


def general_practitioner(username: str, name: str) -> GeneralPractitioner:
    practitioner, _ = GeneralPractitioner.objects.get_or_create(
        user=user(username), defaults={"name": name}
    )
    return practitioner


class Command(SeedCommand):
    help = __doc__

    def seed(self, rows: list[dict[Hashable, Any]]) -> list[str]:
        general_practitioner(GENERAL_PRACTITIONER, GENERAL_PRACTITIONER_NAME)
        for row in rows:
            # Each patient is one NHANES participant; samples start with its number.
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
        return [GENERAL_PRACTITIONER]
