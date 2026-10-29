"""Create demo accounts and patients for manual and browser checks."""

from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from iron_deficiency.dataset import CBC_VARS
from web.accounts.models import User
from web.nhanes.models import Participant
from web.practice.models import GeneralPractitioner, RegisteredSex

PASSWORD = "demo-pass-2026"


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


class Command(BaseCommand):
    help = __doc__

    def handle(self, *args: Any, **options: Any) -> None:
        if not settings.DEBUG:
            raise CommandError(
                "Demo accounts share a known password; run with DJANGO_DEBUG=1."
            )
        with transaction.atomic():
            doctor_a = general_practitioner("doctor-a", "Dr. Demo A")
            doctor_b = general_practitioner("doctor-b", "Dr. Demo B")
            for seqn, (owner, name, sex, age) in enumerate(
                (
                    (doctor_a, "Test Patient 1", RegisteredSex.FEMALE, 32),
                    (doctor_a, "Test Patient 3", RegisteredSex.MALE, 60),
                    (doctor_b, "Test Patient 2", RegisteredSex.FEMALE, 25),
                ),
                start=1,
            ):
                # shortcut: placeholder blood values; NHANES patients replace these next.
                participant, _ = Participant.objects.get_or_create(
                    seqn=seqn, defaults={"cbc": dict.fromkeys(CBC_VARS, 1.0)}
                )
                owner.patients.get_or_create(
                    name=name,
                    defaults={
                        "registered_sex": sex,
                        "age": age,
                        "participant": participant,
                    },
                )
            user("no-role")  # Logged in but neither role: for the refusal page.
        self.stdout.write(
            f"Accounts doctor-a, doctor-b and no-role, password {PASSWORD}"
        )
