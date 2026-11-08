"""The general practitioner's builders: the practitioner, patients, samples and
orders, and the stand-in for a hospital's lab-order endpoint."""

from collections.abc import Iterator
from concurrent import futures
from dataclasses import dataclass
from typing import TYPE_CHECKING

import grpc
import pytest
from pytest_bdd import given, parsers

from tests.conftest import World, make_user
from tests.django_settings import _test_settings
from tests.practice.fake_laboratory import FakeLaboratory
from web.shared.messaging import messages_pb2_grpc

if TYPE_CHECKING:
    from datetime import datetime

    from web.practice.models import Laboratory, Order, Patient, Sample
    from web.shared.accounts.models import User
    from web.shared.vocabulary import ClinicalIndication, RegisteredSex, Test

# The settings every test of this party runs with (tests/django_settings.py).
__all__ = ["_test_settings"]


def make_general_practitioner(name: str) -> "User":
    from web.shared.accounts.roles import Role

    return make_user(name, Role.GENERAL_PRACTITIONER)


def make_patient(name: str, sex: "RegisteredSex", age: int) -> "Patient":
    """A patient of the practice, and three sample IDs of the patient's registered
    sex and age in its stock, as the demo seeds three for each patient."""
    from web.practice.models import Patient

    stock_sample_ids(3, sex, age)
    return Patient.objects.create(name=name, registered_sex=sex, age=age)


def stock_sample_ids(count: int, sex: "RegisteredSex", age: int) -> list[str]:
    """Add `count` new sample IDs of this registered sex and age to the stock."""
    from web.practice.models import SampleId

    first = 100001 + SampleId.objects.count()
    return [
        SampleId.objects.create(value=str(number), registered_sex=sex, age=age).value
        for number in range(first, first + count)
    ]


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
    from web.shared.vocabulary import RegisteredSex

    owner = world["general_practitioners"].get(
        general_practitioner
    ) or make_general_practitioner(general_practitioner)
    world["general_practitioners"][general_practitioner] = owner
    world["patients"][patient] = make_patient(
        patient, RegisteredSex(sex or "female"), int(age or 30)
    )


def suggest_ferritin_on(sample: "Sample", now: "datetime") -> None:
    """The sample's CBC, placed if missing, with a fetched lab report suggesting
    ferritin: what any ferritin order needs (features/practice/ordering.feature). The CBC counts as sent, so no
    test sends it to a laboratory by accident."""
    from web.practice.models import LabReport, Order
    from web.shared.vocabulary import ClinicalIndication, Test

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


def a_laboratory() -> "Laboratory":
    """The practice's first laboratory; one that answers nothing if it works with none yet."""
    from web.practice.models import Laboratory

    laboratory = Laboratory.objects.order_by("pk").first()
    if laboratory is None:
        laboratory = Laboratory.objects.create(
            name="Test Laboratory", address="127.0.0.1:1"
        )
    return laboratory


def collect_and_order(
    *,
    patient: "Patient",
    test: "Test",
    indication: "ClinicalIndication | None",
    now: "datetime",
) -> "Order":
    """Collect a sample from the patient and order one test on it."""
    sample = patient.collect_sample(laboratory=a_laboratory(), now=now)
    if test.on_suspicion():
        suggest_ferritin_on(sample, now)
    return sample.place_order(
        test=test,
        indication=indication,
        now=now,
    )


@dataclass(frozen=True)
class Running:
    laboratory: FakeLaboratory
    address: str


@pytest.fixture
def fake_laboratory() -> Iterator[Running]:
    """A hospital's lab-order endpoint stand-in (tests/practice/fake_laboratory.py),
    running; it and its address."""
    laboratory = FakeLaboratory()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
    messages_pb2_grpc.add_LaboratoryServicer_to_server(laboratory, server)
    port = server.add_insecure_port("127.0.0.1:0")
    server.start()
    yield Running(laboratory, f"127.0.0.1:{port}")
    server.stop(grace=None)
