"""Scenarios: lab orders and lab reports between the general practitioner's app
and the hospital, over gRPC with mutual TLS (features/messaging.feature)."""

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import grpc
import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from tests.conftest import World, make_general_practitioner, make_patient
from tools.certificates import Authority, issue, make_authority
from web.lab import services as lab_services
from web.lab.models import LabOrder
from web.messaging import client, messages_pb2
from web.messaging.client import Connection
from web.messaging.server import serve
from web.practice import services as practice_services
from web.practice.models import LabReport, Order
from web.vocabulary import ClinicalIndication, RegisteredSex
from web.vocabulary import Test as OrderedTest

NOW = datetime(2026, 10, 30, 10, 0, tzinfo=UTC)
# The server runs in its own threads, so the test may not hold a transaction.
pytestmark = pytest.mark.django_db(transaction=True)

scenarios("messaging.feature")


@pytest.fixture
def hospital(tmp_path: Path) -> Iterator[dict[str, object]]:
    authority = make_authority(tmp_path / "az-diest-ca", "AZ Diest")
    certificate, key = issue(authority, tmp_path / "server", "localhost", server=True)
    server, port = serve(
        "127.0.0.1:0",
        certificate=certificate.read_bytes(),
        private_key=key.read_bytes(),
        client_authority=authority.certificate.read_bytes(),
    )
    yield {"authority": authority, "address": f"127.0.0.1:{port}", "tmp": tmp_path}
    server.stop(grace=None)


def connection(hospital: dict[str, object], authority: Authority | None) -> Connection:
    """A client of the hospital, holding a certificate from `authority`, if any."""
    server_authority = hospital["authority"]
    assert isinstance(server_authority, Authority)
    tmp = hospital["tmp"]
    assert isinstance(tmp, Path)
    certificate = key = None
    if authority is not None:
        certificate, key = issue(
            authority, tmp / authority.name, "client", server=False
        )
    return Connection(
        address=str(hospital["address"]),
        root_certificate=server_authority.certificate.read_bytes(),
        certificate=certificate.read_bytes() if certificate else None,
        private_key=key.read_bytes() if key else None,
    )


@given(parsers.parse('hospital "{name}" with its certificate authority'))
def hospital_ready(world: World, hospital: dict[str, object], name: str) -> None:
    world["hospital"] = hospital


@given(
    parsers.parse(
        'general practitioner "{name}" of practice "{practice}",'
        ' with a client certificate from "{hospital_name}"'
    )
)
def general_practitioner(
    world: World, name: str, practice: str, hospital_name: str
) -> None:
    world["general_practitioners"][name] = make_general_practitioner(name)
    hospital = world["hospital"]
    authority = hospital["authority"]
    world["connection"] = connection(hospital, authority)


@given(
    parsers.parse(
        'patient "{patient}" of "{owner}", registered sex {sex}, aged {age:d}'
    )
)
def patient(world: World, patient: str, owner: str, sex: str, age: int) -> None:
    world["patients"][patient] = make_patient(
        world["general_practitioners"][owner], patient, RegisteredSex(sex), age
    )


def order(
    world: World, patient: str, test: OrderedTest, indication: str | None
) -> Order:
    record = world["patients"][patient]
    choice = (
        {c.label.lower(): c for c in ClinicalIndication}[indication]
        if indication
        else None
    )
    placed: Order = practice_services.place_order(
        general_practitioner=record.general_practitioner,
        patient=record,
        test=test,
        indication=choice,
        now=NOW,
    )
    world["order"] = placed
    return placed


@when(
    parsers.re(
        r'"(?P<owner>[^"]+)" orders a CBC for "(?P<patient>[^"]+)"'
        r" with indication (?P<indication>.+)$"
    )
)
@given(
    parsers.re(
        r'"(?P<owner>[^"]+)" ordered a CBC for "(?P<patient>[^"]+)"'
        r" with indication (?P<indication>.+)$"
    )
)
def orders_cbc(world: World, owner: str, patient: str, indication: str) -> None:
    order(world, patient, OrderedTest.CBC, indication)
    client.send_pending_lab_orders(world["connection"], now=NOW)


@when("the same lab order is sent again")
def send_again(world: World) -> None:
    client.send_lab_order(world["order"], world["connection"])


@given(parsers.parse("a client with {certificate}"))
def other_client(world: World, tmp_path: Path, certificate: str) -> None:
    hospital = world["hospital"]
    authorities = {
        "no certificate": None,
        "a certificate from another hospital's authority": make_authority(
            tmp_path / "uz-leuven-ca", "UZ Leuven"
        ),
        "a certificate from the startup's authority": make_authority(
            tmp_path / "startup-ca", "Demo startup"
        ),
    }
    world["connection"] = connection(hospital, authorities[certificate])


@when(parsers.parse('it sends a lab order to "{name}"'))
def sends_lab_order(world: World) -> None:
    unsent = order(world, "Test Patient 1", OrderedTest.CBC, "other")
    try:
        client.send_lab_order(unsent, world["connection"])
    except grpc.RpcError as error:
        world["refused"] = error


@given(parsers.parse('"{name}" released a lab report for the sample of "{patient}"'))
def released(world: World, name: str, patient: str) -> None:
    order(world, patient, OrderedTest.FERRITIN, None)
    client.send_pending_lab_orders(world["connection"], now=NOW)
    lab_order = LabOrder.objects.select_related("sample").get(
        sample__sample_id=world["patients"][patient].sample_id
    )
    lab_services.receive(sample=lab_order.sample, now=NOW)
    lab_services.run_analyser(lab_order=lab_order, now=NOW)


@when("the general practitioner's app checks for lab reports")
@given("the general practitioner's app checked for lab reports")
def checks(world: World) -> None:
    client.check_for_lab_reports(world["connection"], now=NOW)


@then(parsers.parse('"{name}" has a lab order for the sample of "{patient}"'))
def has_lab_order(world: World, name: str, patient: str) -> None:
    sample_id = world["patients"][patient].sample_id
    assert LabOrder.objects.filter(sample__sample_id=sample_id).exists()


@then(parsers.parse('"{name}" has one lab order for the sample of "{patient}"'))
def has_one_lab_order(world: World, name: str, patient: str) -> None:
    sample_id = world["patients"][patient].sample_id
    assert LabOrder.objects.filter(sample__sample_id=sample_id).count() == 1


@then(
    parsers.parse(
        "the lab order holds sample ID, test, clinical indication, registered sex,"
        ' age and "{owner}"'
    )
)
def lab_order_holds(world: World, owner: str) -> None:
    lab_order = LabOrder.objects.select_related("sample").get()
    placed = world["order"]
    assert lab_order.sample.sample_id == placed.sample_id
    assert (lab_order.test, lab_order.indication) == (placed.test, placed.indication)
    assert (lab_order.registered_sex, lab_order.age) == (
        placed.registered_sex,
        placed.age,
    )
    assert lab_order.general_practitioner == owner


@then("the connection is refused")
def connection_refused(world: World) -> None:
    assert world["refused"].code() == grpc.StatusCode.UNAVAILABLE


@then(parsers.parse('"{name}" has no lab order from it'))
def no_lab_order(world: World, name: str) -> None:
    assert not LabOrder.objects.exists()


@then(parsers.parse('"{owner}" has the lab report of "{patient}"'))
def has_lab_report(world: World, owner: str, patient: str) -> None:
    assert LabReport.objects.filter(order__patient=world["patients"][patient]).exists()


@then(parsers.parse('"{owner}" has one lab report of "{patient}"'))
def has_one_lab_report(world: World, owner: str, patient: str) -> None:
    reports = LabReport.objects.filter(order__patient=world["patients"][patient])
    assert reports.count() == 1


@then("the lab order has no field for a patient's name or blood values")
def lab_order_fields() -> None:
    fields = {field.name for field in messages_pb2.LabOrder.DESCRIPTOR.fields}
    assert fields == {
        "sample_id",
        "test",
        "indication",
        "registered_sex",
        "age",
        "general_practitioner",
        "ordered_at",
    }


@then("the lab report has no field for a score or a screening result")
def lab_report_fields() -> None:
    fields = {field.name for field in messages_pb2.LabReport.DESCRIPTOR.fields}
    assert fields == {
        "report_id",
        "sample_id",
        "test",
        "results",
        "comment",
        "released_at",
    }
