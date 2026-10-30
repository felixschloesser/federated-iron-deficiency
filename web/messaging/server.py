"""The hospital's messaging endpoint: gRPC with mutual TLS (spec §10, R22-R25)."""

import functools
from collections.abc import Callable
from concurrent import futures

import grpc
from django.db import close_old_connections
from django.utils import timezone

from web.lab import services
from web.lab.models import LabOrder
from web.messaging import messages_pb2, messages_pb2_grpc
from web.messaging.forms import LabOrderForm


def request[**P, R](handler: Callable[P, R]) -> Callable[P, R]:
    """Open and close the database connection around a call, as Django does per request."""

    @functools.wraps(handler)
    def handle(*args: P.args, **kwargs: P.kwargs) -> R:
        close_old_connections()
        try:
            return handler(*args, **kwargs)
        finally:
            close_old_connections()

    return handle


class Laboratory(messages_pb2_grpc.LaboratoryServicer):
    """Receives lab orders and hands out lab reports, like a view: form, service."""

    @request
    def SendLabOrder(
        self, request: messages_pb2.LabOrder, context: grpc.ServicerContext
    ) -> messages_pb2.Received:
        form = LabOrderForm(
            {
                "sample_id": request.sample_id,
                "test": request.test,
                "indication": request.indication,
                "registered_sex": request.registered_sex,
                "age": request.age,
                "general_practitioner": request.general_practitioner,
                "ordered_at": request.ordered_at,
            }
        )
        if not form.is_valid():
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, form.errors.as_json())
        services.record_lab_order(**form.cleaned_data)
        return messages_pb2.Received()

    @request
    def FetchNewLabReports(
        self, request: messages_pb2.FetchLabReports, context: grpc.ServicerContext
    ) -> messages_pb2.LabReports:
        released = LabOrder.objects.filter(
            analysed_at__isnull=False, report_acknowledged_at__isnull=True
        ).select_related("sample")
        return messages_pb2.LabReports(
            reports=[
                messages_pb2.LabReport(
                    report_id=str(lab_order.pk),
                    sample_id=lab_order.sample.sample_id,
                    test=lab_order.test,
                    results=lab_order.results or {},
                    released_at=lab_order.analysed_at.isoformat()
                    if lab_order.analysed_at
                    else "",
                )
                for lab_order in released
            ]
        )

    @request
    def AcknowledgeLabReports(
        self, request: messages_pb2.Acknowledgement, context: grpc.ServicerContext
    ) -> messages_pb2.Received:
        services.acknowledge_lab_reports(
            report_ids=[int(report_id) for report_id in request.report_ids],
            now=timezone.now(),
        )
        return messages_pb2.Received()


def serve(
    address: str, *, certificate: bytes, private_key: bytes, client_authority: bytes
) -> tuple[grpc.Server, int]:
    """Start the endpoint; only clients certified by `client_authority` get in (R24)."""
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    messages_pb2_grpc.add_LaboratoryServicer_to_server(Laboratory(), server)
    credentials = grpc.ssl_server_credentials(
        [(private_key, certificate)],
        root_certificates=client_authority,
        require_client_auth=True,
    )
    port = server.add_secure_port(address, credentials)
    server.start()
    return server, port
