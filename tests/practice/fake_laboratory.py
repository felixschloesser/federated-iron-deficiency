"""A hospital's lab-order endpoint for the general practitioner's tests, kept
to the messages tests/hospital/test_messaging.py holds the real one to: it
records each lab order it is sent, and hands out the lab reports it was given
until they are acknowledged. No hospital code, no hospital database."""

from dataclasses import dataclass, field
from datetime import datetime

import grpc

from shared.messaging import messages_pb2, messages_pb2_grpc
from shared.messaging.convert import timestamp


@dataclass
class FakeLaboratory(messages_pb2_grpc.LaboratoryServicer):
    lab_orders: list[messages_pb2.LabOrder] = field(default_factory=list)
    reports: dict[str, messages_pb2.LabReport] = field(default_factory=dict)
    acknowledged: set[str] = field(default_factory=set)
    # A status the endpoint answers every lab order with instead of recording it.
    refusal: grpc.StatusCode | None = None

    def release(
        self,
        sample_id: str,
        test: "messages_pb2.Test.ValueType",
        released_at: datetime,
        *,
        ferritin_suggested: bool = False,
    ) -> str:
        """A lab report the hospital releases on a sample; its report ID."""
        report_id = str(len(self.reports) + 1)
        self.reports[report_id] = messages_pb2.LabReport(
            report_id=report_id,
            sample_id=sample_id,
            test=test,
            results={"LBXFER": 11.0},
            ferritin_suggested=ferritin_suggested,
            released_at=timestamp(released_at),
        )
        return report_id

    def SendLabOrder(
        self, request: messages_pb2.LabOrder, context: grpc.ServicerContext
    ) -> messages_pb2.Received:
        if self.refusal is not None:
            context.abort(self.refusal, "refused")
        self.lab_orders.append(request)
        return messages_pb2.Received()

    def FetchNewLabReports(
        self, request: messages_pb2.NewLabReportsRequest, context: grpc.ServicerContext
    ) -> messages_pb2.LabReports:
        return messages_pb2.LabReports(
            reports=[
                report
                for report_id, report in self.reports.items()
                if report_id not in self.acknowledged
            ]
        )

    def AcknowledgeLabReports(
        self, request: messages_pb2.Acknowledgement, context: grpc.ServicerContext
    ) -> messages_pb2.Received:
        self.acknowledged.update(request.report_ids)
        return messages_pb2.Received()
