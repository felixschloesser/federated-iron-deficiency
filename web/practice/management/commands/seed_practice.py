"""Create the practice's demo general practitioner and its NHANES patients."""

from collections.abc import Hashable
from typing import Any

from web.accounts.roles import Role
from web.practice.models import Patient
from web.seeding.accounts import GENERAL_PRACTITIONER
from web.seeding.command import SeedCommand, patient_name, user
from web.vocabulary import RegisteredSex


class Command(SeedCommand):
    help = __doc__

    def seed(self, rows: list[dict[Hashable, Any]]) -> list[str]:
        user(GENERAL_PRACTITIONER, Role.GENERAL_PRACTITIONER)
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
