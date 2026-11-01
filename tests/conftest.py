"""Shared givens for the scenarios, and builders for the view tests."""

from typing import TYPE_CHECKING, Any

import pytest
from pytest_bdd import given, parsers

# The models are imported inside the builders too, so a missing app fails only
# the tests that use it.
if TYPE_CHECKING:
    from web.deployment.models import LaboratoryDirector
    from web.lab.models import LaboratoryStaffMember, LabOrder
    from web.practice.models import GeneralPractitioner, Order, Patient
from web.vocabulary import RegisteredSex

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
    """A patient whose sample ID is a new NHANES number; the hospital's analyser
    stand-in holds placeholder values for it and no ferritin."""
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
        nhanes_number=str(participant.seqn),
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
    from web.vocabulary import RegisteredSex

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


def make_laboratory_director(name: str) -> "LaboratoryDirector":
    from web.accounts.models import User
    from web.deployment.models import LaboratoryDirector

    user = User.objects.create_user(username=name.lower().replace(" ", "-"))
    return LaboratoryDirector.objects.create(user=user, name=name)


def deliver(order: "Order") -> "LabOrder":
    """The lab order (DF24) arriving at the hospital, as its messaging endpoint records it."""
    from web.lab.services import LabOrderDetails, record_lab_order
    from web.vocabulary import ClinicalIndication, RegisteredSex, Test

    return record_lab_order(
        client="client",
        details=LabOrderDetails(
            sample_id=order.sample.sample_id,
            test=Test(order.test),
            indication=ClinicalIndication(order.indication)
            if order.indication
            else None,
            registered_sex=RegisteredSex(order.registered_sex),
            age=order.age,
            general_practitioner=order.sample.patient.general_practitioner.name,
            ordered_at=order.ordered_at,
        ),
    )
