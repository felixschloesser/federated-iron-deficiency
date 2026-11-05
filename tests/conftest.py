"""Shared givens for the scenarios, and builders for the view tests."""

from typing import TYPE_CHECKING, Any

import pytest
from pytest_bdd import given, parsers

# The models are imported inside the builders too, so a missing app fails only
# the tests that use it.
if TYPE_CHECKING:
    from datetime import datetime
    from pathlib import Path

    import pandas as pd

    from web.deployment.models import LaboratoryDirector
    from web.lab.models import LaboratoryStaffMember, LabOrder
    from web.practice.models import GeneralPractitioner, Order, Patient, Sample
    from web.training.models import DataScientist
    from web.vocabulary import ClinicalIndication, Test
from iron_deficiency.cohort import CBC_VARS, FEATURES
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
    from iron_deficiency.cohort import CBC_VARS
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


def make_data_scientist(name: str) -> "DataScientist":
    from web.accounts.models import User
    from web.training.models import DataScientist

    user = User.objects.create_user(username=name.lower().replace(" ", "-"))
    return DataScientist.objects.create(user=user, name=name)


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
    ferritin: what any ferritin order needs (features/ordering.feature). The CBC counts as sent, so no
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

    # The practice's first laboratory, if it works with any (features/messaging.feature).
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


def write_final_model(
    directory: "Path",
    run_id: str,
    validation: dict[str, float],
    stored_at: "datetime",
    leave_out: tuple[str, ...] = (),
    n_features: int = len(FEATURES),
) -> "Path":
    """A final model as the ClientApp stores it (iron_deficiency.final_models)."""
    import torch

    from iron_deficiency.task import Net

    contents = {
        "state_dict": Net(n_features=n_features).state_dict(),
        "mean": torch.zeros(len(FEATURES)),
        "std": torch.ones(len(FEATURES)),
        "threshold": 0.5,
        "run_id": run_id,
        "stored_at": stored_at.isoformat(),
        "federated": {"eval_auroc": 0.87},
        "local_validation": validation,
    }
    for key in leave_out:
        del contents[key]
    path = directory / f"{run_id}.pt"
    torch.save(contents, path)
    return path


# (sex, age, ferritin) per group, in the order seeding.Group lists them.
PEOPLE = [
    ("Female", 30, 8.0),  # eligible, ferritin below 15
    ("Female", 25, 40.0),  # eligible, ferritin 15 or more
    ("Male", 35, None),  # men
    ("Female", 70, None),  # women outside 18-49
]
# Eligible women whom NHANES did not measure: never seeded.
UNMEASURED = ("Female", 40, None)


def nhanes_rows() -> "pd.DataFrame":
    """Four participants per group, so the seed has to choose."""
    import pandas as pd

    rows = [
        {
            "sample_id": 1000 + 10 * group + copy,
            "sex": sex,
            "age": age,
            **dict.fromkeys(CBC_VARS, float(group)),
            "LBXFER": ferritin,
        }
        for group, (sex, age, ferritin) in enumerate([*PEOPLE, UNMEASURED])
        for copy in range(4)
    ]
    return pd.DataFrame(rows)
