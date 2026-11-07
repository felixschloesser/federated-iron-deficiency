"""Scenarios: the hospital's lab-order endpoint, over gRPC, driven as a
practice's app would drive it (features/hospital/messaging.feature). No
general practitioner's code: the messages are built from the proto."""

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import grpc
import pytest
from django.core.management import call_command
from pytest_bdd import given, parsers, scenarios, then, when

from hospital.lab.messaging import serve
from hospital.lab.models import (
    LabOrderDetails,
    Practice,
    Sample,
    ScreeningResult,
    TestRequest,
)
from hospital.nhanes.models import Participant
from shared.messaging import messages_pb2, messages_pb2_grpc
from shared.messaging.convert import timestamp
from shared.vocabulary import RegisteredSex
from shared.vocabulary import Test as OrderedTest
from tests.conftest import World

NOW = datetime(2026, 10, 30, 10, 0, tzinfo=UTC)
TESTS = {"CBC": messages_pb2.TEST_CBC, "ferritin": messages_pb2.TEST_FERRITIN}
SEXES = {
    "female": messages_pb2.REGISTERED_SEX_FEMALE,
    "male": messages_pb2.REGISTERED_SEX_MALE,
}
# The server runs in its own threads, so the test may not hold a transaction.
pytestmark = pytest.mark.django_db(transaction=True)

scenarios("hospital/messaging.feature")


@pytest.fixture
def hospital() -> Iterator[str]:
    """The hospital's endpoint, running; its address."""
    server, port = serve("127.0.0.1:0")
    yield f"127.0.0.1:{port}"
    server.stop(grace=None)


def call(world: World, method: str, request: Any) -> Any:
    """One call of the endpoint, as a practice's app makes it; a refusal is kept."""
    with grpc.insecure_channel(world["hospital"]) as channel:
        endpoint = messages_pb2_grpc.LaboratoryStub(channel)
        try:
            return getattr(endpoint, method)(request, timeout=10)
        except grpc.RpcError as error:
            world["refused"] = error
            return None


@given(parsers.parse('hospital "{name}"'))
def hospital_ready(world: World, hospital: str, name: str) -> None:
    world["hospital"] = hospital


@given(
    parsers.parse(
        '"{name}" knows practice "{practice}" by certificate name "{certificate_name}"'
    )
)
def knows_practice(name: str, practice: str, certificate_name: str) -> None:
    """The hospital registered the practice, and issued its app the name."""
    Practice.objects.add(certificate_name=certificate_name, name=practice)


SENDS = (
    r'practice "(?P<certificate_name>[^"]*)" (?:sends|sent) a lab order for a'
    r' (?P<test>CBC|ferritin) on sample "(?P<sample_id>[^"]+)", indication'
    r" (?P<screened>screened|not screened), registered sex (?P<sex>\w+),"
    r" aged (?P<age>\d+)$"
)


@when(parsers.re(SENDS))
@given(parsers.re(SENDS))
def sends(
    world: World,
    certificate_name: str,
    test: str,
    sample_id: str,
    screened: str,
    sex: str,
    age: str,
) -> None:
    world["sent"] = messages_pb2.LabOrder(
        certificate_name=certificate_name,
        sample_id=sample_id,
        test=TESTS[test],
        screened_indication=screened == "screened",
        registered_sex=SEXES[sex],
        age=int(age),
        ordered_at=timestamp(NOW),
    )
    call(world, "SendLabOrder", world["sent"])


@when(parsers.parse('a lab order that names no practice is sent to "{name}"'))
def sends_without_practice(world: World) -> None:
    sends(world, "", "CBC", "1-1", "not screened", "female", "32")


@when(
    parsers.parse(
        'practice "{certificate_name}", which "{name}" does not know, sends a lab order'
    )
)
def sends_from_unknown_practice(world: World, certificate_name: str) -> None:
    sends(world, certificate_name, "CBC", "1-1", "not screened", "female", "32")


@then(parsers.parse('"{name}" has a lab order for sample "{sample_id}"'))
def has_lab_order(name: str, sample_id: str) -> None:
    assert TestRequest.objects.filter(sample__sample_id=sample_id).exists()


@then(parsers.parse('"{name}" has one lab order for sample "{sample_id}"'))
def has_one_lab_order(name: str, sample_id: str) -> None:
    assert TestRequest.objects.filter(sample__sample_id=sample_id).count() == 1


@then(
    parsers.parse(
        "the lab order holds sample ID, test, whether its indication is screened,"
        ' registered sex and age, from certificate name "{certificate_name}"'
    )
)
def lab_order_holds(world: World, certificate_name: str) -> None:
    test_request = TestRequest.objects.select_related("sample__practice").get()
    sent = world["sent"]
    assert test_request.sample.sample_id == sent.sample_id
    assert (test_request.test, test_request.screened_indication) == (
        OrderedTest.CBC,
        True,
    )
    assert (test_request.registered_sex, test_request.age) == (RegisteredSex.FEMALE, 32)
    assert test_request.ordered_at == NOW
    # The practice by the certificate name it sent; no general practitioner.
    assert test_request.sample.practice.certificate_name == certificate_name


@then("no lab order names a clinical indication")
def names_no_indication() -> None:
    # What the hospital stores (DS8) has no field for it: the laboratory never
    # learns why a CBC was ordered; the message (DF23) has none either.
    assert TestRequest.objects.exists()
    assert "indication" not in {field.name for field in TestRequest._meta.get_fields()}
    assert "indication" not in messages_pb2.LabOrder.DESCRIPTOR.fields_by_name


@then("it is refused as practice required")
def refused_practice_required(world: World) -> None:
    assert world["refused"].code() == grpc.StatusCode.INVALID_ARGUMENT
    assert world["refused"].details() == "practice_required"


@then("it is refused as unknown practice")
def refused_unknown_practice(world: World) -> None:
    assert world["refused"].code() == grpc.StatusCode.PERMISSION_DENIED
    assert world["refused"].details() == "unknown_practice"


@then(parsers.parse('"{name}" has no lab order'))
def no_lab_order(name: str) -> None:
    assert not TestRequest.objects.exists()


def release(sample_id: str, certificate_name: str, test: OrderedTest) -> TestRequest:
    """A lab order of the practice, analysed: its lab report released at once."""
    Participant.objects.get_or_create(
        seqn=int(sample_id.split("-")[0]), defaults={"cbc": {}}
    )
    test_request = TestRequest.objects.receive(
        practice=Practice.objects.get(certificate_name=certificate_name),
        details=LabOrderDetails(
            sample_id=sample_id,
            test=test,
            screened_indication=test.takes_indication(),
            registered_sex=RegisteredSex.FEMALE,
            age=32,
            ordered_at=NOW,
        ),
    )
    return test_request.run_analyser(directory=None, now=NOW)


@given(
    parsers.parse(
        '"{name}" released a ferritin lab report on sample "{sample_id}"'
        ' of practice "{certificate_name}"'
    )
)
def released(name: str, sample_id: str, certificate_name: str) -> None:
    release(sample_id, certificate_name, OrderedTest.FERRITIN)


@given(
    parsers.parse(
        '"{name}" released a CBC lab report with ferritin suggested on sample'
        ' "{sample_id}" of practice "{certificate_name}"'
    )
)
def released_suggested(name: str, sample_id: str, certificate_name: str) -> None:
    test_request = release(sample_id, certificate_name, OrderedTest.CBC)
    # As the deployed model would have decided (features/hospital/screening.feature).
    TestRequest.objects.filter(pk=test_request.pk).update(
        screening_result=ScreeningResult.FERRITIN_SUGGESTED, not_screened_reason=None
    )


@when(parsers.parse('practice "{certificate_name}" fetches its new lab reports'))
def fetches(world: World, certificate_name: str) -> None:
    world["received"] = call(
        world,
        "FetchNewLabReports",
        messages_pb2.NewLabReportsRequest(certificate_name=certificate_name),
    )


def report_id(sample_id: str) -> str:
    return str(TestRequest.objects.get(sample__sample_id=sample_id).pk)


ACKNOWLEDGES = (
    r'practice "(?P<certificate_name>[^"]+)" (?:acknowledges|acknowledged) the'
    r' lab report on sample "(?P<sample_id>[^"]+)"$'
)


@when(parsers.re(ACKNOWLEDGES))
@given(parsers.re(ACKNOWLEDGES))
def acknowledges(world: World, certificate_name: str, sample_id: str) -> None:
    call(
        world,
        "AcknowledgeLabReports",
        messages_pb2.Acknowledgement(
            certificate_name=certificate_name, report_ids=[report_id(sample_id)]
        ),
    )


@then(parsers.parse('it receives the lab report on sample "{sample_id}"'))
def receives_report(world: World, sample_id: str) -> None:
    (report,) = world["received"].reports
    assert (report.report_id, report.sample_id) == (report_id(sample_id), sample_id)
    assert report.test == messages_pb2.TEST_FERRITIN
    assert report.HasField("released_at")


@then(parsers.parse('the lab report on sample "{sample_id}" has ferritin suggested'))
def report_suggests_ferritin(world: World, sample_id: str) -> None:
    (report,) = world["received"].reports
    assert report.sample_id == sample_id
    assert report.ferritin_suggested is True


@then("it receives no lab reports")
def receives_none(world: World) -> None:
    assert list(world["received"].reports) == []


@then(parsers.parse('the lab report on sample "{sample_id}" is still new at "{name}"'))
def still_new(sample_id: str, name: str) -> None:
    test_request = TestRequest.objects.get(sample__sample_id=sample_id)
    assert test_request.report_acknowledged_at is None


@then(parsers.parse('"{name}" has two samples with sample ID "{sample_id}"'))
def two_samples(name: str, sample_id: str) -> None:
    assert Sample.objects.filter(sample_id=sample_id).count() == 2


@then(
    "the lab order has no field for a patient's name or blood values,"
    " only the practice's certificate name"
)
def lab_order_fields() -> None:
    fields = {field.name for field in messages_pb2.LabOrder.DESCRIPTOR.fields}
    assert fields == {
        "certificate_name",
        "sample_id",
        "test",
        "screened_indication",
        "registered_sex",
        "age",
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


# Every call of the service, from its descriptor, so a new one is covered too.
CALLS = list(messages_pb2.DESCRIPTOR.services_by_name["Laboratory"].methods)


@pytest.mark.parametrize("method", CALLS, ids=[method.name for method in CALLS])
def test_every_message_from_a_practice_the_hospital_does_not_know_is_refused(
    hospital: str, method: Any
) -> None:
    request = getattr(messages_pb2, method.input_type.name)(certificate_name="de-linde")
    with grpc.insecure_channel(hospital) as channel:
        endpoint = messages_pb2_grpc.LaboratoryStub(channel)
        with pytest.raises(grpc.RpcError) as refusal:
            getattr(endpoint, method.name)(request, timeout=10)
    assert refusal.value.code() == grpc.StatusCode.PERMISSION_DENIED


def test_add_practice_adds_it_then_changes_its_name() -> None:
    """The hospital registers each practice it works with by the certificate name
    it issued (glossary.toml); the name shown can change, the key cannot."""
    call_command("add_practice", "de-ceder", "Huisartsenpraktijk De Ceder")
    call_command("add_practice", "de-ceder", "Groepspraktijk De Ceder")
    practice = Practice.objects.get()
    assert (practice.certificate_name, practice.name) == (
        "de-ceder",
        "Groepspraktijk De Ceder",
    )
