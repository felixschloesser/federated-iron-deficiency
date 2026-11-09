"""A hospital's lab-order endpoint for the general practitioner's tests, kept
to the messages tests/hospital/test_grpc_server.py holds the real one to: it
records each lab order it is sent, and hands out the lab reports it was given
until they are acknowledged. No hospital code, no hospital database."""

from dataclasses import dataclass, field
from datetime import datetime

import google.rpc.code_pb2 as rpc_code
import google.rpc.error_details_pb2 as rpc_details
import google.rpc.status_pb2 as rpc_status_pb2
import grpc
from google.protobuf import any_pb2
from grpc_status import rpc_status

from web.shared.grpc import messages_pb2, messages_pb2_grpc
from web.shared.grpc.convert import timestamp


def named(context: grpc.ServicerContext) -> str | None:
    """The slug a call named its party by, read as any server reads it."""
    name = dict(context.invocation_metadata()).get("party")
    return name if isinstance(name, str) else None


def rejection(violations: list[tuple[str, str]]) -> grpc.Status:
    """INVALID_ARGUMENT with each violation in a google.rpc.BadRequest detail."""
    detail = any_pb2.Any()
    detail.Pack(
        rpc_details.BadRequest(
            field_violations=[
                rpc_details.BadRequest.FieldViolation(
                    field=name, description=description
                )
                for name, description in violations
            ]
        )
    )
    return rpc_status.to_status(
        rpc_status_pb2.Status(
            code=rpc_code.INVALID_ARGUMENT,
            message="lab_order_rejected",
            details=[detail],
        )
    )


@dataclass
class FakeLaboratory(messages_pb2_grpc.LaboratoryServicer):
    lab_orders: list[messages_pb2.LabOrder] = field(default_factory=list)
    reports: dict[int, messages_pb2.LabReport] = field(default_factory=dict)
    acknowledged: set[int] = field(default_factory=set)
    # The slug each call named its party by, in order.
    callers: list[str | None] = field(default_factory=list)
    # A status the endpoint answers every lab order with instead of recording it.
    refusal: grpc.StatusCode | None = None
    # Samples whose lab order the laboratory rejects: (field, description) each,
    # as google.rpc.BadRequest field violations, the way a laboratory says why.
    rejects: dict[str, list[tuple[str, str]]] = field(default_factory=dict)

    def release(
        self,
        sample_id: str,
        test: "messages_pb2.Test.ValueType",
        released_at: datetime,
        *,
        ferritin_suggested: bool = False,
    ) -> int:
        """A lab report the hospital releases on a sample; its report ID."""
        report_id = len(self.reports) + 1
        self.reports[report_id] = messages_pb2.LabReport(
            report_id=report_id,
            sample_id=sample_id,
            test=test,
            results=[
                messages_pb2.Result(name=messages_pb2.RESULT_NAME_FERRITIN, value=11.0)
            ],
            ferritin_suggested=ferritin_suggested,
            released_at=timestamp(released_at),
        )
        return report_id

    def SendLabOrder(
        self, request: messages_pb2.SendLabOrderRequest, context: grpc.ServicerContext
    ) -> messages_pb2.SendLabOrderResponse:
        self.callers.append(named(context))
        if self.refusal is not None:
            context.abort(self.refusal, "refused")
        lab_order = request.lab_order
        if lab_order.sample_id in self.rejects:
            context.abort_with_status(rejection(self.rejects[lab_order.sample_id]))
        self.lab_orders.append(lab_order)
        return messages_pb2.SendLabOrderResponse()

    def FetchNewLabReports(
        self,
        request: messages_pb2.FetchNewLabReportsRequest,
        context: grpc.ServicerContext,
    ) -> messages_pb2.FetchNewLabReportsResponse:
        self.callers.append(named(context))
        return messages_pb2.FetchNewLabReportsResponse(
            lab_reports=[
                report
                for report_id, report in self.reports.items()
                if report_id not in self.acknowledged
            ]
        )

    def AcknowledgeLabReports(
        self,
        request: messages_pb2.AcknowledgeLabReportsRequest,
        context: grpc.ServicerContext,
    ) -> messages_pb2.AcknowledgeLabReportsResponse:
        self.callers.append(named(context))
        self.acknowledged.update(request.report_ids)
        return messages_pb2.AcknowledgeLabReportsResponse()
