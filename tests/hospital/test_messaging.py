"""The hospital's lab-order endpoint over gRPC, called as a practice's app calls
it: the proto's messages in, status codes out (web/shared/messaging/messages.proto).
Like a view test: what it records and refuses, not the rules behind it, which
are features/hospital/lab_orders.feature. No general practitioner's code."""

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import grpc
import pytest
from django.core.management import call_command
from google.protobuf.empty_pb2 import Empty
from google.protobuf.message_factory import GetMessageClass

from web.hospital.analyser.models import Participant
from web.hospital.lab.messaging import serve
from web.hospital.lab.models import (
    LabOrderDetails,
    Practice,
    ScreeningResult,
    TestRequest,
)
from web.shared.messaging import messages_pb2, messages_pb2_grpc
from web.shared.messaging.convert import timestamp
from web.shared.vocabulary import RegisteredSex
from web.shared.vocabulary import Test as OrderedTest

NOW = datetime(2026, 10, 30, 10, 0, tzinfo=UTC)
# The server runs in its own threads, so the test may not hold a transaction.
pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def endpoint() -> Iterator[messages_pb2_grpc.LaboratoryStub]:
    """The hospital's endpoint, running, knowing practice "de-ceder"; a stub on it."""
    Practice.objects.add(certificate_name="de-ceder", name="De Ceder")
    server, port = serve("127.0.0.1:0")
    with grpc.insecure_channel(f"127.0.0.1:{port}") as channel:
        yield messages_pb2_grpc.LaboratoryStub(channel)
    server.stop(grace=None)


# Each call names its practice in the call's metadata, as the app does.
DE_CEDER = (("certificate-name", "de-ceder"),)


def lab_order(**fields: Any) -> messages_pb2.LabOrder:
    """A lab order for a CBC, screened; `fields` override."""
    values: dict[str, Any] = {
        "sample_id": "1-1",
        "test": messages_pb2.TEST_CBC,
        "screened_indication": True,
        "registered_sex": messages_pb2.REGISTERED_SEX_FEMALE,
        "age": 32,
        "ordered_at": timestamp(NOW),
    } | fields
    return messages_pb2.LabOrder(**values)


def refusal(call: Any, request: Any, metadata: Any = DE_CEDER) -> grpc.RpcError:
    with pytest.raises(grpc.RpcError) as refused:
        call(request, timeout=10, metadata=metadata)
    return refused.value


def test_a_lab_order_is_recorded_as_sent(
    endpoint: messages_pb2_grpc.LaboratoryStub,
) -> None:
    endpoint.SendLabOrder(lab_order(), timeout=10, metadata=DE_CEDER)
    test_request = TestRequest.objects.select_related("sample__practice").get()
    assert test_request.sample.sample_id == "1-1"
    assert (test_request.test, test_request.screened_indication) == (
        OrderedTest.CBC,
        True,
    )
    assert (test_request.registered_sex, test_request.age) == (RegisteredSex.FEMALE, 32)
    assert test_request.ordered_at == NOW
    # The practice by the certificate name it called as; no general practitioner.
    assert test_request.sample.practice.certificate_name == "de-ceder"


def test_a_lab_order_without_a_test_is_refused(
    endpoint: messages_pb2_grpc.LaboratoryStub,
) -> None:
    """The hospital's form checks every field the message carries."""
    refused = refusal(
        endpoint.SendLabOrder, lab_order(test=messages_pb2.TEST_UNSPECIFIED)
    )
    assert refused.code() == grpc.StatusCode.INVALID_ARGUMENT
    assert '"test"' in (refused.details() or "")
    assert not TestRequest.objects.exists()


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
        metadata=(("certificate-name", "de-linde"),),
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
            sample_id="1-1",
            test=OrderedTest.CBC,
            screened_indication=True,
            registered_sex=RegisteredSex.FEMALE,
            age=32,
            ordered_at=NOW,
        ),
    ).run_analyser(directory=None, now=NOW)
    # As the deployed model would have decided (features/hospital/screening.feature).
    TestRequest.objects.filter(pk=test_request.pk).update(
        screening_result=ScreeningResult.FERRITIN_SUGGESTED, not_screened_reason=None
    )
    (report,) = endpoint.FetchNewLabReports(
        Empty(), timeout=10, metadata=DE_CEDER
    ).reports
    assert (report.report_id, report.sample_id) == (str(test_request.pk), "1-1")
    assert report.test == messages_pb2.TEST_CBC
    assert report.ferritin_suggested is True
    assert report.released_at.ToDatetime(tzinfo=UTC) == NOW

    endpoint.AcknowledgeLabReports(
        messages_pb2.Acknowledgement(report_ids=[report.report_id]),
        timeout=10,
        metadata=DE_CEDER,
    )
    fetched = endpoint.FetchNewLabReports(Empty(), timeout=10, metadata=DE_CEDER)
    assert list(fetched.reports) == []


@pytest.mark.django_db
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
