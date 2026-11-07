"""The hospital's messaging endpoint: gRPC, plaintext in the demo (shared/messaging/messages.proto)."""

import grpc
from django.db import models
from django.utils import timezone

from hospital.lab.forms import LabOrderForm
from hospital.lab.models import LabOrderDetails, Practice, TestRequest
from shared.messaging import messages_pb2, messages_pb2_grpc
from shared.messaging.convert import from_proto, moment, timestamp, to_proto
from shared.messaging.endpoint import start, with_database
from shared.vocabulary import RegisteredSex, Test


def _value(choice: models.TextChoices | None) -> str:
    """A choice as the form reads it; empty for none, which a required field refuses."""
    return "" if choice is None else choice.value


type FromPractice = (
    messages_pb2.LabOrder
    | messages_pb2.NewLabReportsRequest
    | messages_pb2.Acknowledgement
)


def practice_of(request: FromPractice, context: grpc.ServicerContext) -> Practice:
    """The calling practice, by the certificate name it sends; a message without
    one, or from a practice the hospital does not know, is refused before anything
    is read or recorded. With the report's mutual TLS
    the name would come from the connection, context.peer_identities()."""
    if not request.certificate_name:
        context.abort(grpc.StatusCode.INVALID_ARGUMENT, "practice_required")
    practice = Practice.objects.filter(
        certificate_name=request.certificate_name
    ).first()
    if practice is None:
        context.abort(grpc.StatusCode.PERMISSION_DENIED, "unknown_practice")
    return practice


class LaboratoryService(messages_pb2_grpc.LaboratoryServicer):
    """Receives lab orders and hands out lab reports, like a view: form, service."""

    @with_database
    def SendLabOrder(
        self, request: messages_pb2.LabOrder, context: grpc.ServicerContext
    ) -> messages_pb2.Received:
        practice = practice_of(request, context)
        form = LabOrderForm(
            {
                "sample_id": request.sample_id,
                "test": _value(from_proto(request.test, messages_pb2.Test, Test)),
                "screened_indication": request.screened_indication,
                "registered_sex": _value(
                    from_proto(
                        request.registered_sex,
                        messages_pb2.RegisteredSex,
                        RegisteredSex,
                    )
                ),
                "age": request.age,
                "ordered_at": moment(request.ordered_at)
                if request.HasField("ordered_at")
                else None,
            }
        )
        if not form.is_valid():
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, form.errors.as_json())
        TestRequest.objects.receive(
            practice=practice,
            details=LabOrderDetails(**form.cleaned_data),
        )
        return messages_pb2.Received()

    @with_database
    def FetchNewLabReports(
        self, request: messages_pb2.NewLabReportsRequest, context: grpc.ServicerContext
    ) -> messages_pb2.LabReports:
        practice = practice_of(request, context)
        return messages_pb2.LabReports(
            reports=[
                messages_pb2.LabReport(
                    report_id=str(test_request.pk),
                    sample_id=test_request.sample.sample_id,
                    test=to_proto(Test(test_request.test), messages_pb2.Test),
                    results=test_request.results or {},
                    ferritin_suggested=test_request.ferritin_suggested,
                    released_at=timestamp(test_request.analysed_at),
                )
                for test_request in TestRequest.objects.reports_to_send(practice)
                if test_request.analysed_at is not None
            ]
        )

    @with_database
    def AcknowledgeLabReports(
        self, request: messages_pb2.Acknowledgement, context: grpc.ServicerContext
    ) -> messages_pb2.Received:
        TestRequest.objects.acknowledge(
            practice=practice_of(request, context),
            report_ids=[int(report_id) for report_id in request.report_ids],
            now=timezone.now(),
        )
        return messages_pb2.Received()


def serve(address: str) -> tuple[grpc.Server, int]:
    """Start the endpoint, plaintext: the demo leaves out the report's mutual TLS."""
    return start(
        address,
        lambda server: messages_pb2_grpc.add_LaboratoryServicer_to_server(
            LaboratoryService(), server
        ),
    )
