"""Send the reasons for rejecting a lab order over gRPC, and read them back.

The laboratory answers INVALID_ARGUMENT with a google.rpc.BadRequest detail that
holds one field violation per validation error the hospital's models raised on
the lab order. The practice shows them as the reason for rejection. WHO LQMS
5-4 (p. 66) asks the laboratory to "record the reason for rejection" and to
"promptly inform the authorized person"."""

import google.rpc.code_pb2 as rpc_code
import google.rpc.error_details_pb2 as rpc_details
import google.rpc.status_pb2 as rpc_status_pb2
import grpc
from django.core.exceptions import ValidationError
from google.protobuf import any_pb2
from grpc_status import rpc_status

MESSAGE = "rejected"


def rejected(error: ValidationError) -> grpc.Status:
    """Build the gRPC status that rejects a message such as a lab order: one field
    violation per error, with the error's code as the reason and its message as
    the description."""
    detail = any_pb2.Any()
    detail.Pack(
        rpc_details.BadRequest(
            field_violations=[
                rpc_details.BadRequest.FieldViolation(
                    field=field,
                    reason=violation.code or "",
                    description=" ".join(violation.messages),
                )
                for field, violations in error.error_dict.items()
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
    """Return the laboratory's reasons as "field: description", joined by "; ".

    Returns None for a failure that names no field: that is a failure of the
    whole call, not a rejection of the lab order."""
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
