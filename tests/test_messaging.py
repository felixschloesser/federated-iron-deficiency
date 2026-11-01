"""Scenarios: lab orders and lab reports between the general practitioner's app
and the hospital, over gRPC with mutual TLS (features/messaging.feature)."""

import shutil
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import grpc
import pytest
from django.core.management import CommandError, call_command
from django.test import Client
from django.urls import reverse
from pytest_bdd import given, parsers, scenarios, then, when
from pytest_django.asserts import assertContains, assertNotContains
from pytest_django.fixtures import Settings

from tests.conftest import World, make_general_practitioner, make_patient
from tools.certificates import Authority, issue, make_authority
from web.lab import services as lab_services
from web.lab.messaging import serve
from web.lab.models import LabOrder, Sample
from web.messaging import messages_pb2
from web.nhanes.models import Participant
from web.practice import messaging
from web.practice import services as practice_services
from web.practice.messaging import Connection
from web.practice.models import GeneralPractitioner, LabReport, Order, Patient
from web.practice.models import Sample as PracticeSample
from web.vocabulary import ClinicalIndication, RegisteredSex
from web.vocabulary import Test as OrderedTest

NOW = datetime(2026, 10, 30, 10, 0, tzinfo=UTC)
# The server runs in its own threads, so the test may not hold a transaction.
pytestmark = pytest.mark.django_db(transaction=True)


def latest_sample_id(patient: Patient) -> str:
    """The sample ID of the patient's latest sample."""
    return patient.samples.latest("pk").sample_id


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


def connection(
    hospital: dict[str, object], authority: Authority | None, name: str = "client"
) -> Connection:
    """A client of the hospital, holding a certificate named `name` from
    `authority`, if any."""
    server_authority = hospital["authority"]
    assert isinstance(server_authority, Authority)
    tmp = hospital["tmp"]
    assert isinstance(tmp, Path)
    certificate = key = None
    if authority is not None:
        certificate, key = issue(authority, tmp / name, name, server=False)
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
    world["connection"] = connection(hospital, authority, practice)


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
    messaging.send_pending_lab_orders(world["connection"], now=NOW)


@when("the same lab order is sent again")
def send_again(world: World) -> None:
    messaging.send_lab_order(world["order"], world["connection"])


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
        messaging.send_lab_order(unsent, world["connection"])
    except grpc.RpcError as error:
        world["refused"] = error


@given(parsers.parse('"{name}" released a lab report for the sample of "{patient}"'))
def released(world: World, name: str, patient: str) -> None:
    order(world, patient, OrderedTest.FERRITIN, None)
    messaging.send_pending_lab_orders(world["connection"], now=NOW)
    lab_order = LabOrder.objects.select_related("sample").get(
        sample__sample_id=latest_sample_id(world["patients"][patient])
    )
    lab_services.run_analyser(lab_order=lab_order, directory=None, now=NOW)


@given(
    parsers.parse(
        '"{name}" released a CBC lab report with ferritin suggested'
        ' for the sample of "{patient}"'
    )
)
def released_suggested(world: World, name: str, patient: str) -> None:
    from web.lab.domain import ScreeningResult

    order(world, patient, OrderedTest.CBC, "unexplained fatigue")
    messaging.send_pending_lab_orders(world["connection"], now=NOW)
    lab_order = LabOrder.objects.select_related("sample").get(
        sample__sample_id=latest_sample_id(world["patients"][patient])
    )
    lab_services.run_analyser(lab_order=lab_order, directory=None, now=NOW)
    # As the deployed model would have decided (features/screening.feature).
    LabOrder.objects.filter(pk=lab_order.pk).update(
        screening_result=ScreeningResult.FERRITIN_SUGGESTED, not_screened_reason=None
    )


@then(
    parsers.parse('the lab report of "{patient}" has ferritin suggested at "{owner}"')
)
def has_ferritin_suggested(world: World, patient: str, owner: str) -> None:
    report = LabReport.objects.get(order__sample__patient=world["patients"][patient])
    assert report.ferritin_suggested is True


@when("the general practitioner's app checks for lab reports")
@given("the general practitioner's app checked for lab reports")
def checks(world: World) -> None:
    messaging.check_for_lab_reports(world["connection"], now=NOW)


@then(parsers.parse('"{name}" has a lab order for the sample of "{patient}"'))
def has_lab_order(world: World, name: str, patient: str) -> None:
    sample_id = latest_sample_id(world["patients"][patient])
    assert LabOrder.objects.filter(sample__sample_id=sample_id).exists()


@then(parsers.parse('"{name}" has one lab order for the sample of "{patient}"'))
def has_one_lab_order(world: World, name: str, patient: str) -> None:
    sample_id = latest_sample_id(world["patients"][patient])
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
    assert lab_order.sample.sample_id == placed.sample.sample_id
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
    assert LabReport.objects.filter(
        order__sample__patient=world["patients"][patient]
    ).exists()


@then(parsers.parse('"{owner}" has one lab report of "{patient}"'))
def has_one_lab_report(world: World, owner: str, patient: str) -> None:
    reports = LabReport.objects.filter(
        order__sample__patient=world["patients"][patient]
    )
    assert reports.count() == 1


@given(
    parsers.parse(
        'another general practitioner\'s app with a client certificate from "{name}"'
    )
)
def other_app(world: World, name: str) -> None:
    world["other"] = connection(
        world["hospital"], world["hospital"]["authority"], "Other app"
    )


@when("the other app checks for lab reports")
def other_checks(world: World) -> None:
    with messaging.open_laboratory(world["other"]) as laboratory:
        world["received"] = laboratory.FetchNewLabReports(
            messages_pb2.FetchLabReports(), timeout=10
        )


@then("it receives no lab reports")
def receives_none(world: World) -> None:
    assert list(world["received"].reports) == []


def lab_order_of(world: World, patient: str) -> LabOrder:
    return LabOrder.objects.get(
        sample__sample_id=latest_sample_id(world["patients"][patient]),
        test=world["order"].test,
    )


@then(parsers.parse('the lab report of "{patient}" is still new at "{name}"'))
def still_new(world: World, patient: str, name: str) -> None:
    assert lab_order_of(world, patient).report_acknowledged_at is None


@then(parsers.parse('the lab report of "{patient}" is no longer new at "{name}"'))
def no_longer_new(world: World, patient: str, name: str) -> None:
    assert lab_order_of(world, patient).report_acknowledged_at is not None


@when(parsers.parse('the other app acknowledges the lab report of "{patient}"'))
def other_acknowledges(world: World, patient: str) -> None:
    with messaging.open_laboratory(world["other"]) as laboratory:
        report_id = str(lab_order_of(world, patient).pk)
        laboratory.AcknowledgeLabReports(
            messages_pb2.Acknowledgement(report_ids=[report_id]), timeout=10
        )


@when(
    parsers.parse('the other app sends a lab order with the sample ID of "{patient}"')
)
def other_sends(world: World, patient: str) -> None:
    messaging.send_lab_order(world["order"], world["other"])


@then(parsers.parse('"{name}" has two samples with the sample ID of "{patient}"'))
def two_samples(world: World, name: str, patient: str) -> None:
    sample_id = latest_sample_id(world["patients"][patient])
    assert Sample.objects.filter(sample_id=sample_id).count() == 2


@given(
    parsers.parse('"{name}" released a lab report for a sample "{owner}" never ordered')
)
def released_unknown(world: World, name: str, owner: str) -> None:
    """A lab order from this app the app itself has no order for."""
    Participant.objects.create(seqn=999999, cbc={})
    stranger = Order(
        sample=PracticeSample(
            patient=world["patients"]["Test Patient 1"],
            sample_id="999999",
            collected_at=NOW,
        ),
        test=OrderedTest.FERRITIN,
        indication=None,
        registered_sex=RegisteredSex.FEMALE,
        age=30,
        ordered_at=NOW,
    )
    messaging.send_lab_order(stranger, world["connection"])
    lab_order = LabOrder.objects.select_related("sample").get(
        sample__sample_id="999999"
    )
    lab_services.run_analyser(lab_order=lab_order, directory=None, now=NOW)


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


@then(
    "the lab report says only whether ferritin is suggested, nothing else of screening"
)
def lab_report_fields() -> None:
    fields = {field.name for field in messages_pb2.LabReport.DESCRIPTOR.fields}
    assert fields == {
        "report_id",
        "sample_id",
        "test",
        "results",
        "ferritin_suggested",
        "released_at",
    }


# The general practitioner's app in use: its views and command talk to the endpoint.


@pytest.fixture
def practice(settings: Settings, hospital: dict[str, object]) -> Path:
    """A practice folder holding the hospital's CA certificate and a client one."""
    authority = hospital["authority"]
    tmp = hospital["tmp"]
    assert isinstance(authority, Authority)
    assert isinstance(tmp, Path)
    certificates = tmp / "practice" / "certificates"
    issue(authority, certificates, "De Ceder", server=False)
    shutil.copy(authority.certificate, certificates / "ca.crt")
    settings.PARTY_DIR = tmp / "practice"
    settings.MESSAGING_ADDRESS = hospital["address"]
    return tmp / "practice"


@pytest.fixture
def owner() -> GeneralPractitioner:
    return make_general_practitioner("Dr. Demo A")


def new_order_url(record: Patient) -> str:
    return reverse(
        "practice:new_order",
        kwargs={"patient": record.pk, "test": OrderedTest.FERRITIN},
    )


def test_placing_an_order_sends_its_lab_order(
    client: Client, practice: Path, owner: GeneralPractitioner
) -> None:
    record = make_patient(owner, "Test Patient 1", RegisteredSex.FEMALE, 32)
    client.force_login(owner.user)
    client.post(new_order_url(record))
    assert LabOrder.objects.filter(sample__sample_id=latest_sample_id(record)).exists()
    assert Order.objects.get().sent_at is not None


def test_an_unreachable_hospital_gets_the_order_with_the_next_check(
    client: Client, settings: Settings, practice: Path, owner: GeneralPractitioner
) -> None:
    settings.MESSAGING_ADDRESS = "127.0.0.1:1"
    record = make_patient(owner, "Test Patient 1", RegisteredSex.FEMALE, 32)
    client.force_login(owner.user)
    response = client.post(new_order_url(record), follow=True)
    assertContains(response, "Ferritin ordered on new sample")
    assertContains(response, "sent with the next check for reports")
    assert Order.objects.get().sent_at is None


def released_ferritin(owner: GeneralPractitioner) -> Patient:
    """A patient whose ferritin the hospital has analysed and released."""
    record = make_patient(owner, "Test Patient 1", RegisteredSex.FEMALE, 32)
    practice_services.place_order(
        general_practitioner=owner,
        patient=record,
        test=OrderedTest.FERRITIN,
        indication=None,
        now=NOW,
    )
    connection = messaging.configured_connection()
    assert connection is not None
    messaging.send_pending_lab_orders(connection, now=NOW)
    lab_order = LabOrder.objects.select_related("sample").get()
    lab_services.run_analyser(lab_order=lab_order, directory=None, now=NOW)
    return record


def test_check_for_reports_fetches_them(
    client: Client, practice: Path, owner: GeneralPractitioner
) -> None:
    record = released_ferritin(owner)
    client.force_login(owner.user)
    response = client.post(reverse("practice:check_for_reports"))
    assert response["Location"] == reverse("practice:orders")
    assertContains(client.get(response["Location"]), "1 new lab report.")
    assert LabReport.objects.filter(order__sample__patient=record).exists()


def test_check_for_reports_is_offered_only_with_a_hospital_to_ask(
    client: Client, settings: Settings, practice: Path, owner: GeneralPractitioner
) -> None:
    client.force_login(owner.user)
    assertContains(client.get(reverse("practice:orders")), "Check for reports")
    settings.MESSAGING_ADDRESS = None
    assertNotContains(client.get(reverse("practice:orders")), "Check for reports")
    assert client.post(reverse("practice:check_for_reports")).status_code == 404


def test_the_command_checks_for_reports(
    practice: Path, owner: GeneralPractitioner
) -> None:
    record = released_ferritin(owner)
    call_command("check_for_lab_reports")
    assert LabReport.objects.filter(order__sample__patient=record).exists()


def test_the_command_needs_a_hospital_to_ask(settings: Settings) -> None:
    settings.MESSAGING_ADDRESS = None
    with pytest.raises(CommandError, match="MESSAGING_ADDRESS"):
        call_command("check_for_lab_reports")
