"""The hospital's lab-order endpoint: gRPC, plaintext in the demo (web/shared/grpc/messages.proto)."""

import grpc
from django.core.exceptions import ValidationError
from django.utils import timezone

from web.hospital.lab.models import LabOrderDetails, Practice, TestRequest
from web.shared.grpc import messages_pb2, messages_pb2_grpc
from web.shared.grpc.convert import from_proto, moment, timestamp, to_proto
from web.shared.grpc.endpoint import start, with_database
from web.shared.grpc.identity import caller
from web.shared.grpc.rejection import rejected
from web.shared.vocabulary import ClinicalIndication, RegisteredSex, ResultName, Test


def practice_of(context: grpc.ServicerContext) -> Practice:
    """The calling practice, by the slug the call names it by; a call that names
    none, or a practice the hospital does not know, is refused before anything is
    read or recorded."""
    slug = caller(context)
    if slug is None:
        context.abort(grpc.StatusCode.UNAUTHENTICATED, "practice_required")
    practice = Practice.objects.filter(slug=slug).first()
    if practice is None:
        context.abort(grpc.StatusCode.PERMISSION_DENIED, "unknown_practice")
    return practice


def lab_order_details(request: messages_pb2.LabOrder) -> LabOrderDetails:
    """What a lab order says, part by part; a part left out is None, for the
    models to refuse (TestRequest.objects.receive)."""
    return LabOrderDetails(
        sample_id=request.sample_id,
        test=from_proto(request.test, messages_pb2.Test, Test),
        clinical_indication=from_proto(
            request.clinical_indication,
            messages_pb2.ClinicalIndication,
            ClinicalIndication,
        ),
        registered_sex=from_proto(
            request.registered_sex, messages_pb2.RegisteredSex, RegisteredSex
        ),
        age=request.age if request.HasField("age") else None,
        ordered_at=moment(request.ordered_at)
        if request.HasField("ordered_at")
        else None,
    )


class LaboratoryService(messages_pb2_grpc.LaboratoryServicer):
    """Receives lab orders and hands out lab reports, like a view: parse, then the
    service."""

    @with_database
    def SendLabOrder(
        self, request: messages_pb2.SendLabOrderRequest, context: grpc.ServicerContext
    ) -> messages_pb2.SendLabOrderResponse:
        practice = practice_of(context)
        try:
            TestRequest.objects.receive(
                practice=practice, details=lab_order_details(request.lab_order)
            )
        except ValidationError as error:
            context.abort_with_status(rejected(error))
        return messages_pb2.SendLabOrderResponse()

    @with_database
    def FetchNewLabReports(
        self,
        request: messages_pb2.FetchNewLabReportsRequest,
        context: grpc.ServicerContext,
    ) -> messages_pb2.FetchNewLabReportsResponse:
        practice = practice_of(context)
        return messages_pb2.FetchNewLabReportsResponse(
            lab_reports=[
                messages_pb2.LabReport(
                    sample_id=test_request.sample.sample_id,
                    test=to_proto(Test(test_request.test), messages_pb2.Test),
                    results=[
                        messages_pb2.Result(
                            name=to_proto(ResultName(name), messages_pb2.ResultName),
                            value=value,
                        )
                        for name, value in (test_request.results or {}).items()
                    ],
                    ferritin_suggested=test_request.ferritin_suggested,
                    released_at=timestamp(test_request.analysed_at),
                )
                for test_request in TestRequest.objects.reports_to_send(practice)
                if test_request.analysed_at is not None
            ]
        )

    @with_database
    def AcknowledgeLabReports(
        self,
        request: messages_pb2.AcknowledgeLabReportsRequest,
        context: grpc.ServicerContext,
    ) -> messages_pb2.AcknowledgeLabReportsResponse:
        practice = practice_of(context)
        try:
            TestRequest.objects.acknowledge(
                practice=practice,
                lab_reports=[
                    (
                        acknowledgement.sample_id,
                        from_proto(acknowledgement.test, messages_pb2.Test, Test),
                    )
                    for acknowledgement in request.acknowledgements
                ],
                now=timezone.now(),
            )
        except ValidationError as error:
            context.abort_with_status(rejected(error))
        return messages_pb2.AcknowledgeLabReportsResponse()


def serve(address: str) -> tuple[grpc.Server, int]:
    """Start the endpoint, plaintext: the demo leaves out the report's mutual TLS."""
    return start(
        address,
        lambda server: messages_pb2_grpc.add_LaboratoryServicer_to_server(
            LaboratoryService(), server
        ),
    )
