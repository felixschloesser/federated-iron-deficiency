"""Shared givens for the scenarios, and builders for the view tests."""

from typing import TYPE_CHECKING, Any

import pytest
from pytest_bdd import given, parsers

# The models are imported inside the builders too, so a missing app fails only
# the tests that use it.
if TYPE_CHECKING:
    from web.lab.models import LaboratoryStaffMember
    from web.practice.models import GeneralPractitioner, Patient, RegisteredSex

World = dict[str, Any]


@pytest.fixture
def world() -> World:
    """What the steps of one scenario have built so far, by name."""
    return {"general_practitioners": {}, "patients": {}}


def make_general_practitioner(name: str) -> "GeneralPractitioner":
    from web.accounts.models import User
    from web.practice.models import GeneralPractitioner

    user = User.objects.create_user(username=name.lower().replace(" ", "-"))
    return GeneralPractitioner.objects.create(user=user, name=name)


def make_patient(
    general_practitioner: "GeneralPractitioner",
    name: str,
    sex: "RegisteredSex",
    age: int,
) -> "Patient":
    """A patient with an NHANES participant of placeholder values and no ferritin."""
    from iron_deficiency.dataset import CBC_VARS
    from web.nhanes.models import Participant
    from web.practice.models import Patient

    participant = Participant.objects.create(
        seqn=Participant.objects.count() + 1, cbc=dict.fromkeys(CBC_VARS, 1.0)
    )
    return Patient.objects.create(
        general_practitioner=general_practitioner,
        name=name,
        registered_sex=sex,
        age=age,
        participant=participant,
    )


@given(
    parsers.re(
        r'general practitioner "(?P<general_practitioner>[^"]+)" with patient "(?P<patient>[^"]+)"'
        r"(?:, registered sex (?P<sex>\w+), aged (?P<age>\d+))?$"
    )
)
def general_practitioner_with_patient(
    world: World,
    db: None,
    general_practitioner: str,
    patient: str,
    sex: str | None,
    age: str | None,
) -> None:
    from web.practice.models import RegisteredSex

    owner = world["general_practitioners"].get(
        general_practitioner
    ) or make_general_practitioner(general_practitioner)
    world["general_practitioners"][general_practitioner] = owner
    world["patients"][patient] = make_patient(
        owner, patient, RegisteredSex(sex or "female"), int(age or 30)
    )


def make_laboratory_staff_member(name: str) -> "LaboratoryStaffMember":
    from web.accounts.models import User
    from web.lab.models import LaboratoryStaffMember

    user = User.objects.create_user(username=name.lower().replace(" ", "-"))
    return LaboratoryStaffMember.objects.create(user=user, name=name)
