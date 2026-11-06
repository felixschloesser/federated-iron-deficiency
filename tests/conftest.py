"""Test-wide settings, shared givens for the scenarios, and builders for the
view tests."""

import copy
from collections.abc import Iterator
from concurrent import futures
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import grpc
import pytest
from pytest_bdd import given, parsers
from pytest_django.fixtures import Settings

# The models are imported inside the builders too, so a missing app fails only
# the tests that use it.
if TYPE_CHECKING:
    from datetime import datetime
    from pathlib import Path

    import pandas as pd

    from web.accounts.models import User
    from web.accounts.roles import Role
    from web.hospital.lab.models import LabOrder, Practice
    from web.hospital.nhanes.models import Participant
    from web.practice.models import Order, Patient, Sample
    from web.vocabulary import ClinicalIndication, Test
from ml.cohort import CBC_VARS, FEATURES
from tests.fake_laboratory import FakeLaboratory
from web.messaging import messages_pb2_grpc
from web.vocabulary import RegisteredSex

World = dict[str, Any]


class MissingVariable(str):
    """Fails the render that would have shown a missing variable as blank."""

    def __mod__(self, name: object) -> str:
        raise AssertionError(f"Template variable missing: {name}")


@pytest.fixture(autouse=True)
def _test_settings(settings: Settings) -> None:
    settings.SECURE_SSL_REDIRECT = False
    # Assign a copy, so Django rebuilds its template engines and restores them after.
    templates = copy.deepcopy(settings.TEMPLATES)
    templates[0]["OPTIONS"]["string_if_invalid"] = MissingVariable("%s")
    settings.TEMPLATES = templates


@pytest.fixture
def world() -> World:
    """What the steps of one scenario have built so far, by name."""
    return {"general_practitioners": {}, "patients": {}}


def make_user(name: str, role: "Role") -> "User":
    from web.accounts.models import User

    return User.objects.create_user(username=name.lower().replace(" ", "-"), role=role)


def make_general_practitioner(name: str) -> "User":
    from web.accounts.roles import Role

    return make_user(name, Role.GENERAL_PRACTITIONER)


def make_patient(name: str, sex: "RegisteredSex", age: int) -> "Patient":
    """A patient of the practice, whose sample IDs start with a new NHANES number."""
    from web.practice.models import Patient

    return Patient.objects.create(
        name=name,
        registered_sex=sex,
        age=age,
        nhanes_number=str(Patient.objects.count() + 1),
    )


def make_tube() -> "Participant":
    """What a new patient's samples would measure at the hospital's analyser
    stand-in: placeholder CBC values, no ferritin. Its number starts their sample IDs."""
    from ml.cohort import CBC_VARS
    from web.hospital.nhanes.models import Participant

    return Participant.objects.create(
        seqn=Participant.objects.count() + 1, cbc=dict.fromkeys(CBC_VARS, 1.0)
    )


def receive_lab_order(
    sample_id: str,
    test: "Test",
    now: "datetime",
    sex: "RegisteredSex" = RegisteredSex.FEMALE,
    age: int = 32,
) -> "LabOrder":
    """A lab order (DF23) as the hospital's messaging endpoint records it, from the
    practice make_practice() adds; a CBC for a screened indication."""
    from web.hospital.lab.models import LabOrder, LabOrderDetails

    return LabOrder.objects.receive(
        practice=make_practice(),
        details=LabOrderDetails(
            sample_id=sample_id,
            test=test,
            screened_indication=test.takes_indication(),
            registered_sex=sex,
            age=age,
            ordered_at=now,
        ),
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
        patient, RegisteredSex(sex or "female"), int(age or 30)
    )


def make_laboratory_staff_member(name: str) -> "User":
    from web.accounts.roles import Role

    return make_user(name, Role.LABORATORY_STAFF)


def make_laboratory_director(name: str) -> "User":
    from web.accounts.roles import Role

    return make_user(name, Role.LABORATORY_DIRECTOR)


def make_data_scientist(name: str) -> "User":
    from web.accounts.roles import Role

    return make_user(name, Role.DATA_SCIENTIST)


def make_practice(certificate_name: str = "practice") -> "Practice":
    """A practice the hospital works with, by its certificate name."""
    from web.hospital.lab.models import Practice

    return Practice.objects.add(
        certificate_name=certificate_name, name=certificate_name.title()
    )


def suggest_ferritin_on(sample: "Sample", now: "datetime") -> None:
    """The sample's CBC, placed if missing, with a fetched lab report suggesting
    ferritin: what any ferritin order needs (features/ordering.feature). The CBC counts as sent, so no
    test sends it to a laboratory by accident."""
    from web.practice.models import LabReport, Order
    from web.vocabulary import ClinicalIndication, Test

    cbc = sample.orders.filter(test=Test.CBC).first()
    if cbc is None:
        cbc = sample.place_order(
            test=Test.CBC, indication=ClinicalIndication.OTHER, now=now
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
    patient: "Patient",
    test: "Test",
    indication: "ClinicalIndication | None",
    now: "datetime",
) -> "Order":
    """Collect a sample from the patient and order one test on it."""
    from web.practice.models import Laboratory

    # The practice's first laboratory, if it works with any (features/practice/messaging.feature).
    laboratory = Laboratory.objects.order_by("pk").first()
    sample = patient.collect_sample(laboratory=laboratory, now=now)
    if test.on_suspicion():
        suggest_ferritin_on(sample, now)
    return sample.place_order(
        test=test,
        indication=indication,
        now=now,
    )


def write_final_model(
    directory: "Path",
    run_id: str,
    validation: dict[float, dict[str, int]],
    stored_at: "datetime",
    local_auroc: float = 0.84,
    leave_out: tuple[str, ...] = (),
    n_features: int = len(FEATURES),
) -> "Path":
    """A final model as the ClientApp stores it (ml.final_models),
    with `validation`, its confusion matrix at each threshold."""
    import torch

    from ml.task import Net

    contents = {
        "state_dict": Net(n_features=n_features).state_dict(),
        "mean": torch.zeros(len(FEATURES)),
        "std": torch.ones(len(FEATURES)),
        "run_id": run_id,
        "stored_at": stored_at.isoformat(),
        "federated": {"eval_auroc": 0.87},
        "confusion_matrices": validation,
        "local_auroc": local_auroc,
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


@dataclass(frozen=True)
class Running:
    laboratory: FakeLaboratory
    address: str


@pytest.fixture
def fake_laboratory() -> Iterator[Running]:
    """A hospital's lab-order endpoint stand-in (tests/fake_laboratory.py),
    running; it and its address."""
    laboratory = FakeLaboratory()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
    messages_pb2_grpc.add_LaboratoryServicer_to_server(laboratory, server)
    port = server.add_insecure_port("127.0.0.1:0")
    server.start()
    yield Running(laboratory, f"127.0.0.1:{port}")
    server.stop(grace=None)
