"""The gRPC contract (web/shared/messaging/messages.proto): the committed
generated code matches it, and its choices and times are typed."""

import subprocess
import sys
from pathlib import Path

import pytest

from web.shared.messaging import GENERATE

ROOT = Path(__file__).resolve().parents[2]
MESSAGING = Path("web", "shared", "messaging")


@pytest.mark.subprocess
def test_the_committed_generated_code_matches_the_proto(tmp_path: Path) -> None:
    """Regenerated with the documented command, every generated file is the
    committed one."""
    command = [arg.replace("=.", f"={tmp_path}") for arg in GENERATE]
    subprocess.run([sys.executable, "-m", *command], cwd=ROOT, check=True)
    for generated in sorted((ROOT / MESSAGING).glob("*_pb2*")):
        regenerated = tmp_path / MESSAGING / generated.name
        assert regenerated.read_text() == generated.read_text(), generated.name


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
    what a field may hold (web/shared/messaging/messages.proto)."""
    from web.shared.messaging import messages_pb2

    descriptor = getattr(messages_pb2, message).DESCRIPTOR.fields_by_name[field]
    typed = descriptor.enum_type or descriptor.message_type
    assert typed is not None, f"{message}.{field} is a {descriptor.type}"
    assert typed.name == kind


# The vocabularies that cross the wire; the clinical indication does not.
VOCABULARIES = ("Test", "RegisteredSex")


def _members() -> list[tuple[str, str]]:
    from web.shared import vocabulary

    return [
        (name, member.name)
        for name in VOCABULARIES
        for member in getattr(vocabulary, name)
    ]


@pytest.mark.parametrize(("vocabulary", "member"), _members())
def test_every_choice_crosses_the_wire_and_back(vocabulary: str, member: str) -> None:
    from web.shared import vocabulary as words
    from web.shared.messaging import messages_pb2
    from web.shared.messaging.convert import from_proto, to_proto

    choices = getattr(words, vocabulary)
    enum = getattr(messages_pb2, vocabulary)
    value = to_proto(choices[member], enum)
    assert value != 0
    assert from_proto(value, enum, choices) is choices[member]


@pytest.mark.parametrize("vocabulary", VOCABULARIES)
def test_none_and_unknown_numbers_are_no_choice(vocabulary: str) -> None:
    from web.shared import vocabulary as words
    from web.shared.messaging import messages_pb2
    from web.shared.messaging.convert import from_proto, to_proto

    choices = getattr(words, vocabulary)
    enum = getattr(messages_pb2, vocabulary)
    assert to_proto(None, enum) == 0
    assert from_proto(0, enum, choices) is None
    assert from_proto(99, enum, choices) is None
    # One proto value per member and UNSPECIFIED: nothing the vocabulary lacks.
    assert len(enum.DESCRIPTOR.values) == len(choices) + 1
