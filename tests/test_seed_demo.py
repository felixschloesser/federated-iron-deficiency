"""The demo data command used for manual and browser checks."""

import pytest
from django.core.management import CommandError, call_command
from pytest_django.fixtures import Settings

from web.accounts.models import User
from web.practice.models import GeneralPractitioner, Patient

pytestmark = pytest.mark.django_db


def test_seeds_general_practitioners_and_their_patients(
    settings: Settings,
) -> None:
    settings.DEBUG = True
    call_command("seed_demo")
    doctor_a = GeneralPractitioner.objects.get(user__username="doctor-a")
    assert sorted(doctor_a.patients.values_list("name", flat=True)) == [
        "Test Patient 1",
        "Test Patient 3",
    ]
    assert User.objects.get(username="no-role").check_password("demo-pass-2026")


def test_running_twice_changes_nothing(settings: Settings) -> None:
    settings.DEBUG = True
    call_command("seed_demo")
    call_command("seed_demo")
    assert User.objects.count() == 3
    assert Patient.objects.count() == 3


def test_refuses_outside_development(settings: Settings) -> None:
    settings.DEBUG = False
    with pytest.raises(CommandError, match="DJANGO_DEBUG=1"):
        call_command("seed_demo")
    assert not User.objects.exists()
