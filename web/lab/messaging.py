"""The hospital's messaging endpoint: gRPC with mutual TLS (spec §10, R22-R25)."""

import functools
from collections.abc import Callable, Iterable, Mapping
from concurrent import futures
from typing import cast

import grpc
from django.db import close_old_connections, models
from django.utils import timezone

from web.lab.forms import LabOrderForm
from web.lab.models import LabOrder, LabOrderDetails
from web.messaging import messages_pb2, messages_pb2_grpc
from web.messaging.choices import from_proto, moment, timestamp, to_proto
from web.vocabulary import ClinicalIndication, RegisteredSex, Test


def with_database[**P, R](handler: Callable[P, R]) -> Callable[P, R]:
    """Open and close the database connection around a call, as Django does per request."""

    @functools.wraps(handler)
    def handle(*args: P.args, **kwargs: P.kwargs) -> R:
        close_old_connections()
        try:
            return handler(*args, **kwargs)
        finally:
            close_old_connections()

    return handle


def _value(choice: models.TextChoices | None) -> str:
    """A choice as the form reads it; empty for none, which a required field refuses."""
    return "" if choice is None else choice.value


def client_of(context: grpc.ServicerContext) -> str:
    """The calling app: its client certificate's common name, which the
    hospital's own certificate authority issued (R24)."""
    # grpc-stubs types the values as bytes; gRPC gives an iterable of bytes,
    # as its documentation and its own aio stubs say.
    names = cast(Mapping[str, Iterable[bytes]], context.auth_context())
    (name,) = names["x509_common_name"]
    return name.decode()


class Laboratory(messages_pb2_grpc.LaboratoryServicer):
    """Receives lab orders and hands out lab reports, like a view: form, service."""

    @with_database
    def SendLabOrder(
        self, request: messages_pb2.LabOrder, context: grpc.ServicerContext
    ) -> messages_pb2.Received:
        form = LabOrderForm(
            {
                "sample_id": request.sample_id,
                "test": _value(from_proto(request.test, messages_pb2.Test, Test)),
                "indication": _value(
                    from_proto(
                        request.indication,
                        messages_pb2.ClinicalIndication,
                        ClinicalIndication,
                    )
                ),
                "registered_sex": _value(
                    from_proto(
                        request.registered_sex,
                        messages_pb2.RegisteredSex,
                        RegisteredSex,
                    )
                ),
                "age": request.age,
                "general_practitioner": request.general_practitioner,
                "ordered_at": moment(request.ordered_at)
                if request.HasField("ordered_at")
                else None,
            }
        )
        if not form.is_valid():
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, form.errors.as_json())
        LabOrder.objects.record(
            client=client_of(context),
            details=LabOrderDetails(**form.cleaned_data),
        )
        return messages_pb2.Received()

    @with_database
    def FetchNewLabReports(
        self, request: messages_pb2.FetchLabReports, context: grpc.ServicerContext
    ) -> messages_pb2.LabReports:
        return messages_pb2.LabReports(
            reports=[
                messages_pb2.LabReport(
                    report_id=str(lab_order.pk),
                    sample_id=lab_order.sample.sample_id,
                    test=to_proto(Test(lab_order.test), messages_pb2.Test),
                    results=lab_order.results or {},
                    ferritin_suggested=lab_order.ferritin_suggested,
                    released_at=timestamp(lab_order.analysed_at),
                )
                for lab_order in LabOrder.objects.reports_to_send(client_of(context))
                if lab_order.analysed_at is not None
            ]
        )

    @with_database
    def AcknowledgeLabReports(
        self, request: messages_pb2.Acknowledgement, context: grpc.ServicerContext
    ) -> messages_pb2.Received:
        LabOrder.objects.acknowledge(
            client=client_of(context),
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
