"""The general practitioner's app as client of each laboratory it works with: lab
orders out, lab reports in (tests/practice/test_grpc_client.py)."""

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
from web.shared.parsing import parsed
from web.shared.vocabulary import ClinicalIndication, RegisteredSex, ResultName, Test

TIMEOUT_SECONDS = 10
# Sending from an order's own request: the general practitioner is waiting.
IN_REQUEST_TIMEOUT_SECONDS = 2


@contextmanager
def open_laboratory(
    laboratory: Laboratory,
) -> Iterator[messages_pb2_grpc.LaboratoryStub]:
    """The hospital's endpoint over a channel that is closed afterwards; plaintext,
    as the demo leaves out the report's mutual TLS."""
    with grpc.insecure_channel(laboratory.address) as channel:
        yield messages_pb2_grpc.LaboratoryStub(channel)


def _send(
    endpoint: messages_pb2_grpc.LaboratoryStub, order: Order, *, timeout: float
) -> None:
    """Send an order's lab order (DF23): no name, no values."""
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
        metadata=calling_as(settings.PRACTICE_NAME),
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
            # One lab order's reason holds back no other; anything else is the
            # whole exchange's, and stops it.
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
    """Send the laboratory the lab orders of its samples it has not confirmed yet,
    over one channel; it records each once (tests/practice/test_grpc_client.py)."""
    with open_laboratory(laboratory) as endpoint:
        return _send_pending(endpoint, laboratory, now=now, timeout=timeout)


def unreachable(error: grpc.RpcError) -> bool:
    """Whether a failed exchange is the network's: wait it out. Anything else the
    hospital refused, which waiting does not mend."""
    match error.code():
        case grpc.StatusCode.UNAVAILABLE | grpc.StatusCode.DEADLINE_EXCEEDED:
            return True
        case _:
            return False


def check_for_lab_reports(laboratory: Laboratory, *, now: datetime) -> int:
    """Send the laboratory its pending lab orders, fetch its new lab reports (DF25),
    store those of its orders and acknowledge every one received, stored or not,
    so none is sent again; the number stored."""
    with open_laboratory(laboratory) as endpoint:
        _send_pending(endpoint, laboratory, now=now)
        metadata = calling_as(settings.PRACTICE_NAME)
        reports = endpoint.FetchNewLabReports(
            messages_pb2.FetchNewLabReportsRequest(),
            timeout=TIMEOUT_SECONDS,
            metadata=metadata,
        ).lab_reports
        stored = sum(_store(report, laboratory, now=now) for report in reports)
        if reports:
            endpoint.AcknowledgeLabReports(
                messages_pb2.AcknowledgeLabReportsRequest(
                    report_ids=[report.report_id for report in reports]
                ),
                timeout=TIMEOUT_SECONDS,
                metadata=metadata,
            )
    return stored


def _store(
    report: messages_pb2.LabReport, laboratory: Laboratory, *, now: datetime
) -> bool:
    """Store a lab report of one of this app's orders on a sample that went to this
    laboratory, as its fields parse it; False if it matches none, or a field
    refuses a part, so the practice never fills a part the hospital left out.

    The hospital is another party: a report that cannot be stored is still
    acknowledged, so it is sent once and holds back no other, and a laboratory
    reports only on the samples it was sent."""
    order = Order.objects.filter(
        sample__sample_id__value=report.sample_id,
        sample__laboratory=laboratory,
        test=from_proto(report.test, messages_pb2.Test, Test),
    ).first()
    if order is None:
        return False
    try:
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
    """One check for lab reports at every laboratory the practice works with."""

    asked: int
    fetched: int
    failures: list[tuple[Laboratory, grpc.RpcError]]


def check_every_laboratory(*, now: datetime) -> Check:
    """Check each laboratory in turn; one that fails holds back no other (tests/practice/test_grpc_client.py)."""
    asked, fetched, failures = 0, 0, []
    for laboratory in Laboratory.objects.order_by("name"):
        asked += 1
        try:
            fetched += check_for_lab_reports(laboratory, now=now)
        except grpc.RpcError as error:
            failures.append((laboratory, error))
    return Check(asked=asked, fetched=fetched, failures=failures)
