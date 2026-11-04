"""Shared givens for the scenarios, and builders for the view tests."""

from typing import TYPE_CHECKING, Any

import pytest
from pytest_bdd import given, parsers

# The models are imported inside the builders too, so a missing app fails only
# the tests that use it.
if TYPE_CHECKING:
    from datetime import datetime

    from web.deployment.models import LaboratoryDirector
    from web.lab.models import LaboratoryStaffMember, LabOrder
    from web.practice.models import GeneralPractitioner, Order, Patient, Sample
    from web.vocabulary import ClinicalIndication, Test
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
    """The lab order (DF23) arriving at the hospital, as its messaging endpoint records it."""
    from web.lab.models import LabOrder, LabOrderDetails
    from web.vocabulary import RegisteredSex, Test

    return LabOrder.objects.record(
        practice="practice",
        details=LabOrderDetails(
            sample_id=order.sample.sample_id,
            test=Test(order.test),
            screened_indication=order.screened_indication,
            registered_sex=RegisteredSex(order.registered_sex),
            age=order.age,
            ordered_at=order.ordered_at,
        ),
    )


def suggest_ferritin_on(sample: "Sample", now: "datetime") -> None:
    """The sample's CBC, placed if missing, with a fetched lab report suggesting
    ferritin: what any ferritin order needs (R11). The CBC counts as sent, so no
    test sends it to a laboratory by accident."""
    from web.practice.models import LabReport, Order
    from web.vocabulary import ClinicalIndication, Test

    cbc = sample.orders.filter(test=Test.CBC).first()
    if cbc is None:
        cbc = sample.patient.general_practitioner.place_order(
            sample=sample, test=Test.CBC, indication=ClinicalIndication.OTHER, now=now
        )
    Order.objects.filter(pk=cbc.pk, sent_at=None).update(sent_at=now)
    LabReport.objects.update_or_create(
        order=cbc,
        defaults={
            "results": {},
            "ferritin_suggested": True,
            "released_at": now,
            "fetched_at": now,
        },
    )


def collect_and_order(
    *,
    general_practitioner: "GeneralPractitioner",
    patient: "Patient",
    test: "Test",
    indication: "ClinicalIndication | None",
    now: "datetime",
) -> "Order":
    """Collect a sample from the patient and order one test on it."""
    from web.practice.models import Laboratory

    # The practice's first laboratory, if it works with any (R22).
    laboratory = Laboratory.objects.order_by("pk").first()
    sample = general_practitioner.collect_sample(
        patient=patient, laboratory=laboratory, now=now
    )
    if test.on_suspicion():
        suggest_ferritin_on(sample, now)
    return general_practitioner.place_order(
        sample=sample,
        test=test,
        indication=indication,
        now=now,
    )
