"""The general practitioner's app as client of each laboratory it works with: lab
orders out, lab reports in (features/practice/messaging.feature)."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime

import grpc
from django.conf import settings

from web.messaging import messages_pb2, messages_pb2_grpc
from web.messaging.convert import from_proto, moment, timestamp, to_proto
from web.practice.models import Laboratory, LabReport, Order
from web.vocabulary import RegisteredSex, Test

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


def send_lab_order(order: Order, laboratory: Laboratory) -> None:
    """Send an order's lab order (DF23): no name, no values (features/practice/messaging.feature)."""
    with open_laboratory(laboratory) as endpoint:
        _send(endpoint, order, timeout=TIMEOUT_SECONDS)


def _send(
    endpoint: messages_pb2_grpc.LaboratoryStub, order: Order, *, timeout: float
) -> None:
    endpoint.SendLabOrder(
        messages_pb2.LabOrder(
            certificate_name=settings.PRACTICE_CERTIFICATE_NAME,
            sample_id=order.sample.sample_id,
            test=to_proto(Test(order.test), messages_pb2.Test),
            screened_indication=order.screened_indication,
            registered_sex=to_proto(
                RegisteredSex(order.registered_sex), messages_pb2.RegisteredSex
            ),
            age=order.age,
            ordered_at=timestamp(order.ordered_at),
        ),
        timeout=timeout,
    )


def _send_pending(
    endpoint: messages_pb2_grpc.LaboratoryStub,
    laboratory: Laboratory,
    *,
    now: datetime,
    timeout: float = TIMEOUT_SECONDS,
) -> int:
    pending = Order.objects.filter(
        sent_at__isnull=True, sample__laboratory=laboratory
    ).select_related("sample__patient")
    for order in pending:
        _send(endpoint, order, timeout=timeout)
        Order.objects.filter(pk=order.pk).update(sent_at=now)
    return len(pending)


def send_pending_lab_orders(
    laboratory: Laboratory,
    *,
    now: datetime,
    timeout: float = TIMEOUT_SECONDS,
) -> int:
    """Send the laboratory the lab orders of its samples it has not confirmed yet,
    over one channel; it records each once (features/practice/messaging.feature)."""
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
    store and acknowledge them."""
    with open_laboratory(laboratory) as endpoint:
        _send_pending(endpoint, laboratory, now=now)
        reports = endpoint.FetchNewLabReports(
            messages_pb2.NewLabReportsRequest(
                certificate_name=settings.PRACTICE_CERTIFICATE_NAME
            ),
            timeout=TIMEOUT_SECONDS,
        ).reports
        stored = [
            report.report_id
            for report in reports
            if _store(report, laboratory, now=now)
        ]
        if stored:
            endpoint.AcknowledgeLabReports(
                messages_pb2.Acknowledgement(
                    certificate_name=settings.PRACTICE_CERTIFICATE_NAME,
                    report_ids=stored,
                ),
                timeout=TIMEOUT_SECONDS,
            )
    return len(stored)


def _store(
    report: messages_pb2.LabReport, laboratory: Laboratory, *, now: datetime
) -> bool:
    """Store a lab report of one of this app's orders on a sample that went to this
    laboratory; False if it matches none.

    The hospital is another party: a report that cannot be stored stays
    unacknowledged instead of holding back the others, and a laboratory reports
    only on the samples it was sent."""
    test = from_proto(report.test, messages_pb2.Test, Test)
    if test is None or not report.HasField("released_at"):
        return False
    released_at = moment(report.released_at)
    order = Order.objects.filter(
        sample__sample_id=report.sample_id,
        sample__laboratory=laboratory,
        test=test,
    ).first()
    if order is None:
        return False
    LabReport.objects.get_or_create(
        order=order,
        defaults={
            "results": dict(report.results),
            "ferritin_suggested": report.ferritin_suggested,
            "released_at": released_at,
            "fetched_at": now,
        },
    )
    return True


@dataclass(frozen=True)
class Check:
    """One check for lab reports at every laboratory the practice works with."""

    asked: int
    fetched: int
    failures: list[tuple[Laboratory, grpc.RpcError]]


def check_every_laboratory(*, now: datetime) -> Check:
    """Check each laboratory in turn; one that fails holds back no other (features/practice/messaging.feature)."""
    asked, fetched, failures = 0, 0, []
    for laboratory in Laboratory.objects.order_by("name"):
        asked += 1
        try:
            fetched += check_for_lab_reports(laboratory, now=now)
        except grpc.RpcError as error:
            failures.append((laboratory, error))
    return Check(asked=asked, fetched=fetched, failures=failures)
