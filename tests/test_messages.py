"""The committed gRPC code matches messages.proto (spec §10, R25)."""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GENERATED = (
    "messages_pb2.py",
    "messages_pb2.pyi",
    "messages_pb2_grpc.py",
    "messages_pb2_grpc.pyi",
)


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
        ("LabOrder", "indication", "ClinicalIndication"),
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
    what a field may hold (spec §10)."""
    from web.messaging import messages_pb2

    descriptor = getattr(messages_pb2, message).DESCRIPTOR.fields_by_name[field]
    typed = descriptor.enum_type or descriptor.message_type
    assert typed is not None, f"{message}.{field} is a {descriptor.type}"
    assert typed.name == kind


VOCABULARIES = ("Test", "ClinicalIndication", "RegisteredSex")


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
    from web.messaging.choices import from_proto, to_proto

    choices = getattr(words, vocabulary)
    enum = getattr(messages_pb2, vocabulary)
    value = to_proto(choices[member], enum)
    assert value != 0
    assert from_proto(value, enum, choices) is choices[member]


@pytest.mark.parametrize("vocabulary", VOCABULARIES)
def test_none_and_unknown_numbers_are_no_choice(vocabulary: str) -> None:
    from web import vocabulary as words
    from web.messaging import messages_pb2
    from web.messaging.choices import from_proto, to_proto

    choices = getattr(words, vocabulary)
    enum = getattr(messages_pb2, vocabulary)
    assert to_proto(None, enum) == 0
    assert from_proto(0, enum, choices) is None
    assert from_proto(99, enum, choices) is None
    # One proto value per member and UNSPECIFIED: nothing the vocabulary lacks.
    assert len(enum.DESCRIPTOR.values) == len(choices) + 1
