"""The hospital's lab-order endpoint over gRPC, called as a practice's app calls
it: the proto's messages in, status codes out (web/shared/grpc/messages.proto).
Like a view test: what it records and refuses, not the rules behind it, which
are features/hospital/lab_orders.feature. No general practitioner's code."""

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import grpc
import pytest
from django.core.management import call_command
from google.protobuf.message_factory import GetMessageClass

from web.hospital.analyser.models import Participant
from web.hospital.lab.grpc_server import serve
from web.hospital.lab.models import (
    LabOrderDetails,
    Practice,
    ScreeningResult,
    TestRequest,
)
from web.shared.grpc import messages_pb2, messages_pb2_grpc
from web.shared.grpc.convert import timestamp
from web.shared.vocabulary import ClinicalIndication, RegisteredSex
from web.shared.vocabulary import Test as OrderedTest

NOW = datetime(2026, 10, 30, 10, 0, tzinfo=UTC)
# The server runs in its own threads, so the test may not hold a transaction.
pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def endpoint() -> Iterator[messages_pb2_grpc.LaboratoryStub]:
    """The hospital's endpoint, running, knowing practice "de-ceder"; a stub on it."""
    Practice.objects.add(name="De Ceder")
    server, port = serve("127.0.0.1:0")
    with grpc.insecure_channel(f"127.0.0.1:{port}") as channel:
        yield messages_pb2_grpc.LaboratoryStub(channel)
    server.stop(grace=None)


# Each call names its practice in the call's metadata, as the app does.
DE_CEDER = (("party", "de-ceder"),)


def lab_order(**fields: Any) -> messages_pb2.LabOrder:
    """A lab order for a CBC, for suspected anaemia; `fields` override."""
    values: dict[str, Any] = {
        "sample_id": "1",
        "test": messages_pb2.TEST_CBC,
        "clinical_indication": messages_pb2.CLINICAL_INDICATION_SUSPECTED_ANAEMIA,
        "registered_sex": messages_pb2.REGISTERED_SEX_FEMALE,
        "age": 32,
        "ordered_at": timestamp(NOW),
    } | fields
    return messages_pb2.LabOrder(**values)


def sent(order: messages_pb2.LabOrder) -> messages_pb2.SendLabOrderRequest:
    return messages_pb2.SendLabOrderRequest(lab_order=order)


def violations(refused: grpc.RpcError) -> list[tuple[str, str]]:
    """A rejected lab order's reasons (WHO LQMS 5-4, p. 66), as the practice
    reads them: INVALID_ARGUMENT with google.rpc.BadRequest field violations,
    each with the model's error code as the reason and a description to show."""
    import google.rpc.error_details_pb2 as rpc_details
    from grpc_status import rpc_status

    assert refused.code() == grpc.StatusCode.INVALID_ARGUMENT
    status = rpc_status.from_call(refused)
    assert status is not None
    bad_request = rpc_details.BadRequest()
    (detail,) = status.details
    assert detail.Unpack(bad_request)
    assert all(violation.description for violation in bad_request.field_violations)
    return [
        (violation.field, violation.reason)
        for violation in bad_request.field_violations
    ]


def refusal(call: Any, request: Any, metadata: Any = DE_CEDER) -> grpc.RpcError:
    with pytest.raises(grpc.RpcError) as refused:
        call(request, timeout=10, metadata=metadata)
    return refused.value


def test_a_lab_order_is_recorded_as_sent(
    endpoint: messages_pb2_grpc.LaboratoryStub,
) -> None:
    endpoint.SendLabOrder(sent(lab_order()), timeout=10, metadata=DE_CEDER)
    test_request = TestRequest.objects.select_related("sample__practice").get()
    assert test_request.sample.sample_id == "1"
    assert (test_request.test, test_request.clinical_indication) == (
        OrderedTest.CBC,
        ClinicalIndication.SUSPECTED_ANAEMIA,
    )
    assert (test_request.registered_sex, test_request.age) == (RegisteredSex.FEMALE, 32)
    assert test_request.ordered_at == NOW
    # The practice its call named, by its name's slug; no general practitioner.
    assert test_request.sample.practice.name == "De Ceder"


# Every part of a lab order but its clinical indication, which ferritin takes
# none of, from the descriptor, so a new part is covered too.
PARTS = [
    field.name
    for field in messages_pb2.LabOrder.DESCRIPTOR.fields
    if field.name != "clinical_indication"
]


@pytest.mark.parametrize("part", PARTS)
def test_a_lab_order_missing_any_part_is_refused(
    endpoint: messages_pb2_grpc.LaboratoryStub, part: str
) -> None:
    """The hospital's models require every part; no age is not age 0."""
    full = lab_order()
    order = messages_pb2.LabOrder(
        **{
            field.name: getattr(full, field.name)
            for field in full.DESCRIPTOR.fields
            if field.name != part
        }
    )
    refused = refusal(endpoint.SendLabOrder, sent(order))
    assert [field for field, _ in violations(refused)] == [part]
    assert not TestRequest.objects.exists()


def test_a_lab_order_for_a_test_the_contract_lacks_is_refused(
    endpoint: messages_pb2_grpc.LaboratoryStub,
) -> None:
    """A number the Test enum does not name is no test."""
    refused = refusal(endpoint.SendLabOrder, sent(lab_order(test=99)))
    assert violations(refused) == [("test", "invalid_choice")]
    assert not TestRequest.objects.exists()


def test_a_lab_order_with_a_sample_id_too_long_is_refused(
    endpoint: messages_pb2_grpc.LaboratoryStub,
) -> None:
    """The sample's model says what a sample ID may be."""
    refused = refusal(endpoint.SendLabOrder, sent(lab_order(sample_id="1" * 21)))
    assert violations(refused) == [("sample_id", "max_length")]
    assert not TestRequest.objects.exists()


def test_a_lab_order_for_a_newborn_is_recorded(
    endpoint: messages_pb2_grpc.LaboratoryStub,
) -> None:
    """Age 0, sent, is an age."""
    endpoint.SendLabOrder(sent(lab_order(age=0)), timeout=10, metadata=DE_CEDER)
    assert TestRequest.objects.get().age == 0


# Every call of the service, from its descriptor, so a new one is covered too.
CALLS = list(messages_pb2.DESCRIPTOR.services_by_name["Laboratory"].methods)


def request_of(method: Any) -> Any:
    """An empty request of the call's own type."""
    return GetMessageClass(method.input_type)()


@pytest.mark.parametrize("method", CALLS, ids=[method.name for method in CALLS])
def test_every_call_that_names_no_practice_is_refused(
    endpoint: messages_pb2_grpc.LaboratoryStub, method: Any
) -> None:
    """The caller must say who it is before anything is read or recorded."""
    refused = refusal(getattr(endpoint, method.name), request_of(method), metadata=())
    assert (refused.code(), refused.details()) == (
        grpc.StatusCode.UNAUTHENTICATED,
        "practice_required",
    )
    assert not TestRequest.objects.exists()


@pytest.mark.parametrize("method", CALLS, ids=[method.name for method in CALLS])
def test_every_call_from_a_practice_the_hospital_does_not_know_is_refused(
    endpoint: messages_pb2_grpc.LaboratoryStub, method: Any
) -> None:
    refused = refusal(
        getattr(endpoint, method.name),
        request_of(method),
        metadata=(("party", "de-linde"),),
    )
    assert (refused.code(), refused.details()) == (
        grpc.StatusCode.PERMISSION_DENIED,
        "unknown_practice",
    )
    assert not TestRequest.objects.exists()


def test_a_released_lab_report_is_fetched_until_acknowledged(
    endpoint: messages_pb2_grpc.LaboratoryStub,
) -> None:
    Participant.objects.create(seqn=1, cbc={})
    test_request = TestRequest.objects.receive(
        practice=Practice.objects.get(),
        details=LabOrderDetails(
            sample_id="1",
            test=OrderedTest.CBC,
            clinical_indication=ClinicalIndication.SUSPECTED_ANAEMIA,
            registered_sex=RegisteredSex.FEMALE,
            age=32,
            ordered_at=NOW,
        ),
    ).run_analyser(directory=None, now=NOW)
    # As the deployed screening model would have decided (features/hospital/screening.feature).
    TestRequest.objects.filter(pk=test_request.pk).update(
        screening_result=ScreeningResult.FERRITIN_SUGGESTED
    )
    (report,) = endpoint.FetchNewLabReports(
        messages_pb2.FetchNewLabReportsRequest(), timeout=10, metadata=DE_CEDER
    ).lab_reports
    assert report.sample_id == "1"
    assert report.test == messages_pb2.TEST_CBC
    assert report.ferritin_suggested is True
    assert report.released_at.ToDatetime(tzinfo=UTC) == NOW

    endpoint.AcknowledgeLabReports(
        messages_pb2.AcknowledgeLabReportsRequest(
            acknowledgements=[
                messages_pb2.Acknowledgement(sample_id="1", test=messages_pb2.TEST_CBC)
            ]
        ),
        timeout=10,
        metadata=DE_CEDER,
    )
    fetched = endpoint.FetchNewLabReports(
        messages_pb2.FetchNewLabReportsRequest(), timeout=10, metadata=DE_CEDER
    )
    assert list(fetched.lab_reports) == []


@pytest.mark.django_db
def test_add_practice_adds_it_once_by_its_name() -> None:
    """The hospital registers each practice it works with by its name, which
    never changes (web/shared/glossary.toml); its slug follows from the name."""
    call_command("add_practice", "Huisartsenpraktijk De Ceder")
    call_command("add_practice", "Huisartsenpraktijk De Ceder")
    practice = Practice.objects.get()
    assert (practice.name, practice.slug) == (
        "Huisartsenpraktijk De Ceder",
        "huisartsenpraktijk-de-ceder",
    )
