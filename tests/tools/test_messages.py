"""The committed gRPC code matches messages.proto (web/messaging/messages.proto, features/practice/messaging.feature)."""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GENERATED = (
    "messages_pb2.py",
    "messages_pb2.pyi",
    "messages_pb2_grpc.py",
    "messages_pb2_grpc.pyi",
)


@pytest.mark.subprocess
def test_generated_code_matches_the_proto(tmp_path: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "generate_messages.py"),
            "--out",
            str(tmp_path),
        ],
        check=True,
    )
    committed = ROOT / "web" / "messaging"
    for name in GENERATED:
        assert (tmp_path / name).read_text() == (committed / name).read_text(), name


@pytest.mark.parametrize(
    ("message", "field", "kind"),
    [
        ("LabOrder", "test", "Test"),
        ("LabOrder", "registered_sex", "RegisteredSex"),
        ("LabOrder", "ordered_at", "Timestamp"),
        ("LabReport", "test", "Test"),
        ("LabReport", "released_at", "Timestamp"),
    ],
)
def test_the_contract_types_choices_and_times(
    message: str, field: str, kind: str
) -> None:
    """Choices are proto enums and times Timestamps, so the contract itself says
    what a field may hold (web/messaging/messages.proto)."""
    from web.messaging import messages_pb2

    descriptor = getattr(messages_pb2, message).DESCRIPTOR.fields_by_name[field]
    typed = descriptor.enum_type or descriptor.message_type
    assert typed is not None, f"{message}.{field} is a {descriptor.type}"
    assert typed.name == kind


# The vocabularies that cross the wire; the clinical indication does not (features/practice/messaging.feature).
VOCABULARIES = ("Test", "RegisteredSex")


def _members() -> list[tuple[str, str]]:
    from web import vocabulary

    return [
        (name, member.name)
        for name in VOCABULARIES
        for member in getattr(vocabulary, name)
    ]


@pytest.mark.parametrize(("vocabulary", "member"), _members())
def test_every_choice_crosses_the_wire_and_back(vocabulary: str, member: str) -> None:
    from web import vocabulary as words
    from web.messaging import messages_pb2
    from web.messaging.convert import from_proto, to_proto

    choices = getattr(words, vocabulary)
    enum = getattr(messages_pb2, vocabulary)
    value = to_proto(choices[member], enum)
    assert value != 0
    assert from_proto(value, enum, choices) is choices[member]


@pytest.mark.parametrize("vocabulary", VOCABULARIES)
def test_none_and_unknown_numbers_are_no_choice(vocabulary: str) -> None:
    from web import vocabulary as words
    from web.messaging import messages_pb2
    from web.messaging.convert import from_proto, to_proto

    choices = getattr(words, vocabulary)
    enum = getattr(messages_pb2, vocabulary)
    assert to_proto(None, enum) == 0
    assert from_proto(0, enum, choices) is None
    assert from_proto(99, enum, choices) is None
    # One proto value per member and UNSPECIFIED: nothing the vocabulary lacks.
    assert len(enum.DESCRIPTOR.values) == len(choices) + 1


def test_a_lab_order_says_whether_its_indication_is_screened_and_nothing_more() -> None:
    """The laboratory needs the indication only to decide whether to screen (features/screening.feature, features/practice/messaging.feature): one yes or no, never which indication, pregnancy included."""
    from google.protobuf.descriptor import FieldDescriptor

    from web.messaging import messages_pb2

    fields = messages_pb2.LabOrder.DESCRIPTOR.fields_by_name
    assert fields["screened_indication"].type == FieldDescriptor.TYPE_BOOL
    assert "indication" not in fields
    assert not hasattr(messages_pb2, "ClinicalIndication")
