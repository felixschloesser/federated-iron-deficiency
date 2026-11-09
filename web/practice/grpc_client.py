"""The practice's gRPC client for each laboratory it works with: it sends lab
orders and fetches lab reports (tests/practice/test_grpc_client.py)."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime

import grpc
from django.conf import settings
from django.core.exceptions import ValidationError

from web.practice.models import Laboratory, LabReport, Order
from web.shared.grpc import messages_pb2, messages_pb2_grpc
from web.shared.grpc.convert import from_proto, moment, timestamp, to_proto
from web.shared.grpc.identity import calling_as
from web.shared.grpc.rejection import reason_for_rejection
from web.shared.parsing import once_each, parsed
from web.shared.vocabulary import ClinicalIndication, RegisteredSex, ResultName, Test

TIMEOUT_SECONDS = 10
# Shorter timeout for sending during the order's own web request, because the
# general practitioner is waiting for the page.
IN_REQUEST_TIMEOUT_SECONDS = 2


@contextmanager
def open_laboratory(
    laboratory: Laboratory,
) -> Iterator[messages_pb2_grpc.LaboratoryStub]:
    """Open a channel to the laboratory's hospital endpoint and close it
    afterwards. The channel is plaintext because the demo leaves out mutual
    TLS."""
    with grpc.insecure_channel(laboratory.address) as channel:
        yield messages_pb2_grpc.LaboratoryStub(channel)


def _send(
    endpoint: messages_pb2_grpc.LaboratoryStub, order: Order, *, timeout: float
) -> None:
    """Send one order's lab order; it carries no patient name and no values."""
    indication = (
        None if order.indication is None else ClinicalIndication(order.indication)
    )
    endpoint.SendLabOrder(
        messages_pb2.SendLabOrderRequest(
            lab_order=messages_pb2.LabOrder(
                sample_id=order.sample.sample_id.value,
                test=to_proto(Test(order.test), messages_pb2.Test),
                clinical_indication=to_proto(
                    indication, messages_pb2.ClinicalIndication
                ),
                registered_sex=to_proto(
                    RegisteredSex(order.registered_sex), messages_pb2.RegisteredSex
                ),
                age=order.age,
                ordered_at=timestamp(order.ordered_at),
            )
        ),
        timeout=timeout,
        metadata=calling_as(settings.PARTY_NAME),
    )


def _send_pending(
    endpoint: messages_pb2_grpc.LaboratoryStub,
    laboratory: Laboratory,
    *,
    now: datetime,
    timeout: float = TIMEOUT_SECONDS,
) -> int:
    pending = (
        Order.objects.not_sent()
        .filter(sample__laboratory=laboratory)
        .select_related("sample__patient", "sample__sample_id")
    )
    sent = 0
    for order in pending:
        try:
            _send(endpoint, order, timeout=timeout)
        except grpc.RpcError as error:
            # A rejection of one lab order does not hold back the others; any
            # other error belongs to the whole exchange and stops it.
            reason = reason_for_rejection(error)
            if reason is None:
                raise
            order.reject(reason=reason, now=now)
            continue
        Order.objects.filter(pk=order.pk).update(sent_at=now)
        sent += 1
    return sent


def send_pending_lab_orders(
    laboratory: Laboratory,
    *,
    now: datetime,
    timeout: float = TIMEOUT_SECONDS,
) -> int:
    """Send the laboratory every lab order for its samples that it has not
    confirmed yet, over one channel; return how many were sent. The laboratory
    records each lab order once, so sending one again is harmless."""
    with open_laboratory(laboratory) as endpoint:
        return _send_pending(endpoint, laboratory, now=now, timeout=timeout)


def unreachable(error: grpc.RpcError) -> bool:
    """Whether a failed exchange is a network failure, which may pass if one
    waits. Any other failure means the hospital refused the message, and
    waiting will not fix it."""
    match error.code():
        case grpc.StatusCode.UNAVAILABLE | grpc.StatusCode.DEADLINE_EXCEEDED:
            return True
        case _:
            return False


def check_for_lab_reports(laboratory: Laboratory, *, now: datetime) -> int:
    """Send the laboratory its pending lab orders, then fetch its new lab reports
    and store those that belong to this practice's orders; return how many were
    stored. Every report received is acknowledged, stored or not, so the
    laboratory does not send it again."""
    with open_laboratory(laboratory) as endpoint:
        _send_pending(endpoint, laboratory, now=now)
        metadata = calling_as(settings.PARTY_NAME)
        reports = endpoint.FetchNewLabReports(
            messages_pb2.FetchNewLabReportsRequest(),
            timeout=TIMEOUT_SECONDS,
            metadata=metadata,
        ).lab_reports
        stored = sum(_store(report, laboratory, now=now) for report in reports)
        if reports:
            endpoint.AcknowledgeLabReports(
                messages_pb2.AcknowledgeLabReportsRequest(
                    acknowledgements=[
                        messages_pb2.Acknowledgement(
                            sample_id=report.sample_id, test=report.test
                        )
                        for report in reports
                    ]
                ),
                timeout=TIMEOUT_SECONDS,
                metadata=metadata,
            )
    return stored


def _store(
    report: messages_pb2.LabReport, laboratory: Laboratory, *, now: datetime
) -> bool:
    """Store a lab report if it belongs to one of this practice's orders on a
    sample sent to this laboratory and every field parses. Return False
    otherwise; the practice never fills in a part the hospital left out.

    The hospital is another party, so its reports are not trusted. A report
    that cannot be stored is still acknowledged, so it is sent only once and
    does not hold back the others. Matching on the laboratory means a
    laboratory can report only on samples sent to it."""
    order = Order.objects.filter(
        sample__sample_id__value=report.sample_id,
        sample__laboratory=laboratory,
        test=from_proto(report.test, messages_pb2.Test, Test),
    ).first()
    if order is None:
        return False
    try:
        once_each(
            "results",
            (result.name for result in report.results),
            code="duplicate_result_name",
        )
        values = parsed(
            (
                LabReport,
                {
                    "results": {
                        from_proto(
                            result.name, messages_pb2.ResultName, ResultName
                        ): result.value if result.HasField("value") else None
                        for result in report.results
                    },
                    "ferritin_suggested": report.ferritin_suggested
                    if report.HasField("ferritin_suggested")
                    else None,
                    "released_at": moment(report.released_at)
                    if report.HasField("released_at")
                    else None,
                },
            )
        )
    except ValidationError:
        return False
    LabReport.objects.get_or_create(order=order, defaults=values | {"fetched_at": now})
    return True


@dataclass(frozen=True)
class Check:
    """The outcome of checking every laboratory for lab reports: how many were
    asked, how many reports were stored, and which laboratories failed."""

    asked: int
    fetched: int
    failures: list[tuple[Laboratory, grpc.RpcError]]


def check_every_laboratory(*, now: datetime) -> Check:
    """Check each laboratory in turn; a failure at one does not stop the others."""
    asked, fetched, failures = 0, 0, []
    for laboratory in Laboratory.objects.order_by("name"):
        asked += 1
        try:
            fetched += check_for_lab_reports(laboratory, now=now)
        except grpc.RpcError as error:
            failures.append((laboratory, error))
    return Check(asked=asked, fetched=fetched, failures=failures)
