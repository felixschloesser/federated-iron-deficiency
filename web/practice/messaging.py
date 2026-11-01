"""The general practitioner's app as client: lab orders out, lab reports in (R22, R23)."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime

import grpc
from django.conf import settings

from web.messaging import messages_pb2, messages_pb2_grpc
from web.practice.models import LabReport, Order

TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class Connection:
    """Where the general practitioner's hospital is, and the app's certificate (R24)."""

    address: str
    root_certificate: bytes
    certificate: bytes | None
    private_key: bytes | None


def configured_connection() -> Connection | None:
    """The practice's connection to its hospital, or None without one to ask."""
    if settings.MESSAGING_ADDRESS is None or settings.PARTY_DIR is None:
        return None
    certificates = settings.PARTY_DIR / "certificates"
    return Connection(
        address=settings.MESSAGING_ADDRESS,
        root_certificate=(certificates / "ca.crt").read_bytes(),
        certificate=(certificates / "certificate.pem").read_bytes(),
        private_key=(certificates / "key.pem").read_bytes(),
    )


@contextmanager
def open_laboratory(
    connection: Connection,
) -> Iterator[messages_pb2_grpc.LaboratoryStub]:
    """The hospital's endpoint over a channel that is closed afterwards."""
    credentials = grpc.ssl_channel_credentials(
        root_certificates=connection.root_certificate,
        private_key=connection.private_key,
        certificate_chain=connection.certificate,
    )
    with grpc.secure_channel(connection.address, credentials) as channel:
        yield messages_pb2_grpc.LaboratoryStub(channel)


def send_lab_order(order: Order, connection: Connection) -> None:
    """Send an order's lab order (DF24): no name, no values (R25)."""
    with open_laboratory(connection) as laboratory:
        laboratory.SendLabOrder(
            messages_pb2.LabOrder(
                sample_id=order.sample_id,
                test=order.test,
                indication=order.indication or "",
                registered_sex=order.registered_sex,
                age=order.age,
                general_practitioner=order.patient.general_practitioner.name,
                ordered_at=order.ordered_at.isoformat(),
            ),
            timeout=TIMEOUT_SECONDS,
        )


def send_pending_lab_orders(connection: Connection, *, now: datetime) -> int:
    """Send every order the hospital has not confirmed yet; it records each once."""
    pending = Order.objects.filter(sent_at__isnull=True).select_related(
        "patient__general_practitioner"
    )
    for order in pending:
        send_lab_order(order, connection)
        Order.objects.filter(pk=order.pk).update(sent_at=now)
    return len(pending)


def check_for_lab_reports(connection: Connection, *, now: datetime) -> int:
    """Send pending orders, fetch new lab reports (DF26), store and acknowledge them."""
    send_pending_lab_orders(connection, now=now)
    with open_laboratory(connection) as laboratory:
        reports = laboratory.FetchNewLabReports(
            messages_pb2.FetchLabReports(), timeout=TIMEOUT_SECONDS
        ).reports
        stored = [report.report_id for report in reports if _store(report, now=now)]
        if stored:
            laboratory.AcknowledgeLabReports(
                messages_pb2.Acknowledgement(report_ids=stored),
                timeout=TIMEOUT_SECONDS,
            )
    return len(stored)


def _store(report: messages_pb2.LabReport, *, now: datetime) -> bool:
    """Store a lab report of one of this app's orders; False if it matches none.

    The hospital is another party: a report that cannot be stored stays
    unacknowledged instead of holding back the others."""
    order = Order.objects.filter(sample_id=report.sample_id, test=report.test).first()
    try:
        released_at = datetime.fromisoformat(report.released_at)
    except ValueError:
        return False
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
