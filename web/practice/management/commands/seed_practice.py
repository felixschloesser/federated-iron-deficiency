"""Create the practice's demo general practitioners and their NHANES patients."""

from collections.abc import Hashable
from typing import Any

from web.accounts.demo import SeedCommand, user
from web.practice.models import GeneralPractitioner, Patient
from web.vocabulary import RegisteredSex


def general_practitioner(username: str, name: str) -> GeneralPractitioner:
    practitioner, _ = GeneralPractitioner.objects.get_or_create(
        user=user(username), defaults={"name": name}
    )
    return practitioner


class Command(SeedCommand):
    help = __doc__

    def seed(self, rows: list[dict[Hashable, Any]]) -> list[str]:
        practitioners = [
            general_practitioner("doctor-a", "Dr. Demo A"),
            general_practitioner("doctor-b", "Dr. Demo B"),
        ]
        for number, row in enumerate(rows, start=1):
            # The sample ID is the participant's NHANES number (R26).
            Patient.objects.get_or_create(
                sample_id=str(int(row["sample_id"])),
                defaults={
                    "general_practitioner": practitioners[
                        (number - 1) % len(practitioners)
                    ],
                    "name": f"Test Patient {number}",
                    "registered_sex": RegisteredSex(str(row["sex"]).lower()),
                    "age": int(row["age"]),
                },
            )
        return ["doctor-a", "doctor-b"]
