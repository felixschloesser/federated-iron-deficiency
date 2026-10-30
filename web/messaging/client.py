"""The general practitioner's app as client: lab orders out, lab reports in (R22, R23)."""

from dataclasses import dataclass
from datetime import datetime

import grpc
from django.db import transaction

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


def _laboratory(connection: Connection) -> messages_pb2_grpc.LaboratoryStub:
    credentials = grpc.ssl_channel_credentials(
        root_certificates=connection.root_certificate,
        private_key=connection.private_key,
        certificate_chain=connection.certificate,
    )
    return messages_pb2_grpc.LaboratoryStub(
        grpc.secure_channel(connection.address, credentials)
    )


def send_lab_order(order: Order, connection: Connection) -> None:
    """Send an order's lab order (DF1): no name, no values (R25)."""
    _laboratory(connection).SendLabOrder(
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
    """Send pending orders, fetch new lab reports (DF20), store and acknowledge them."""
    send_pending_lab_orders(connection, now=now)
    laboratory = _laboratory(connection)
    reports = laboratory.FetchNewLabReports(
        messages_pb2.FetchLabReports(), timeout=TIMEOUT_SECONDS
    ).reports
    with transaction.atomic():
        for report in reports:
            order = Order.objects.get(sample_id=report.sample_id, test=report.test)
            LabReport.objects.get_or_create(
                order=order,
                defaults={
                    "results": dict(report.results),
                    "comment": report.comment,
                    "released_at": datetime.fromisoformat(report.released_at),
                    "fetched_at": now,
                },
            )
    if reports:
        laboratory.AcknowledgeLabReports(
            messages_pb2.Acknowledgement(report_ids=[r.report_id for r in reports]),
            timeout=TIMEOUT_SECONDS,
        )
    return len(reports)
