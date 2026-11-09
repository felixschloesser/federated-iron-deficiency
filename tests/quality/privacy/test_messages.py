"""What crosses between practice and hospital: data minimisation
read from the gRPC contract itself, no database and no process. The cheapest
tier: a privacy property the contract decides is tested on the contract."""

import pytest


def test_a_lab_order_names_its_indication_only_as_one_of_the_choices() -> None:
    """The laboratory decides from the clinical indication whether to screen (features/hospital/screening.feature): it learns which of the six choices, pregnancy included, never free text."""
    from google.protobuf.descriptor import FieldDescriptor

    from web.shared.grpc import messages_pb2

    field = messages_pb2.LabOrder.DESCRIPTOR.fields_by_name["clinical_indication"]
    assert field.type == FieldDescriptor.TYPE_ENUM
    assert field.enum_type is messages_pb2.ClinicalIndication.DESCRIPTOR


@pytest.mark.parametrize(
    ("message", "fields"),
    [
        # No patient name, no blood values, no general practitioner: the call's metadata says which practice ordered.
        (
            "LabOrder",
            {
                "sample_id",
                "test",
                "clinical_indication",
                "registered_sex",
                "age",
                "ordered_at",
            },
        ),
        # Of screening, only whether ferritin is suggested: no score, no reason.
        (
            "LabReport",
            {
                "sample_id",
                "test",
                "results",
                "ferritin_suggested",
                "released_at",
            },
        ),
        # A lab report received, named as both parties know it.
        ("Acknowledgement", {"sample_id", "test"}),
    ],
)
def test_a_message_between_practice_and_hospital_carries_only_these_fields(
    message: str, fields: set[str]
) -> None:
    """What crosses from the practice to the hospital and back:
    a new field fails this until it is added here on purpose."""
    from web.shared.grpc import messages_pb2

    descriptor = getattr(messages_pb2, message).DESCRIPTOR
    assert {field.name for field in descriptor.fields} == fields
