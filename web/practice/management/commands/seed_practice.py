"""Create the practice's demo general practitioners and their NHANES patients."""

from collections.abc import Hashable
from typing import Any

from web.accounts.demo import SeedCommand, user
from web.demo_accounts import GENERAL_PRACTITIONERS
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
            general_practitioner(username, name)
            for username, name in GENERAL_PRACTITIONERS.items()
        ]
        for number, row in enumerate(rows, start=1):
            # Each patient is one NHANES participant; samples start with its number.
            Patient.objects.get_or_create(
                nhanes_number=str(int(row["sample_id"])),
                defaults={
                    "general_practitioner": practitioners[
                        (number - 1) % len(practitioners)
                    ],
                    "name": f"Test Patient {number}",
                    "registered_sex": RegisteredSex(str(row["sex"]).lower()),
                    "age": int(row["age"]),
                },
            )
        return list(GENERAL_PRACTITIONERS)
