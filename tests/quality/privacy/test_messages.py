"""What crosses between practice and hospital (DF23, DF25): data minimisation
read from the gRPC contract itself, no database and no process. The cheapest
tier: a privacy property the contract decides is tested on the contract."""

import pytest


def test_a_lab_order_says_whether_its_indication_is_screened_and_nothing_more() -> None:
    """The laboratory needs the indication only to decide whether to screen (features/hospital/screening.feature): one yes or no, never which indication, pregnancy included."""
    from google.protobuf.descriptor import FieldDescriptor

    from web.shared.messaging import messages_pb2

    fields = messages_pb2.LabOrder.DESCRIPTOR.fields_by_name
    assert fields["screened_indication"].type == FieldDescriptor.TYPE_BOOL
    assert "indication" not in fields
    assert not hasattr(messages_pb2, "ClinicalIndication")


@pytest.mark.parametrize(
    ("message", "fields"),
    [
        # No patient name, no blood values, no clinical indication, no general
        # practitioner: the call's metadata says which practice ordered.
        (
            "LabOrder",
            {
                "sample_id",
                "test",
                "screened_indication",
                "registered_sex",
                "age",
                "ordered_at",
            },
        ),
        # Of screening, only whether ferritin is suggested: no score, no reason.
        (
            "LabReport",
            {
                "report_id",
                "sample_id",
                "test",
                "results",
                "ferritin_suggested",
                "released_at",
            },
        ),
    ],
)
def test_a_message_between_practice_and_hospital_carries_only_these_fields(
    message: str, fields: set[str]
) -> None:
    """What crosses from the practice to the hospital and back (DF23, DF25):
    a new field fails this until it is added here on purpose."""
    from web.shared.messaging import messages_pb2

    descriptor = getattr(messages_pb2, message).DESCRIPTOR
    assert {field.name for field in descriptor.fields} == fields
