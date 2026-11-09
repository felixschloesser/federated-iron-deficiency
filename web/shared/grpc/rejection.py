"""A rejected lab order's reasons on the wire (WHO LQMS 5-4, p. 66: "Record the
reason for rejection", "promptly inform the authorized person"): the laboratory
answers INVALID_ARGUMENT with a google.rpc.BadRequest detail, one field
violation per rule of the contract the lab order breaks (protovalidate), and the
practice reads them back as its reason for rejection
(web/shared/grpc/messages.proto)."""

import google.rpc.code_pb2 as rpc_code
import google.rpc.error_details_pb2 as rpc_details
import google.rpc.status_pb2 as rpc_status_pb2
import grpc
import protovalidate
from google.protobuf import any_pb2
from grpc_status import rpc_status

MESSAGE = "lab_order_rejected"


def _field(violation: protovalidate.Violation) -> str:
    """The part a violation names, as a dotted path."""
    path = violation.proto.field
    return "" if path is None else ".".join(e.field_name for e in path.elements)


def rejected(violations: list[protovalidate.Violation]) -> grpc.Status:
    """The status rejecting a lab order: each violation, by field, its rule as
    the reason and its message as the description."""
    detail = any_pb2.Any()
    detail.Pack(
        rpc_details.BadRequest(
            field_violations=[
                rpc_details.BadRequest.FieldViolation(
                    field=_field(violation),
                    reason=violation.proto.rule_id,
                    description=violation.proto.message,
                )
                for violation in violations
            ]
        )
    )
    return rpc_status.to_status(
        rpc_status_pb2.Status(
            code=rpc_code.INVALID_ARGUMENT, message=MESSAGE, details=[detail]
        )
    )


def reason_for_rejection(error: grpc.RpcError) -> str | None:
    """The laboratory's reasons, "field: description" each; None for a failure
    that names no field, which is the whole exchange's, not one lab order's."""
    status = rpc_status.from_call(error)
    if status is None or status.code != rpc_code.INVALID_ARGUMENT:
        return None
    reasons = []
    for detail in status.details:
        bad_request = rpc_details.BadRequest()
        if detail.Unpack(bad_request):
            reasons += [
                f"{violation.field}: {violation.description}"
                for violation in bad_request.field_violations
            ]
    return "; ".join(reasons) or None
