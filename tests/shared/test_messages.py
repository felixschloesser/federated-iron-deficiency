"""The gRPC contract (web/shared/messaging/messages.proto): the committed
generated code matches it, and its choices and times are typed."""

import subprocess
import sys
from pathlib import Path

import pytest

from web.shared.messaging import GENERATE

ROOT = Path(__file__).resolve().parents[2]
MESSAGING = Path("web", "shared", "messaging")
VALIDATE = Path("buf", "validate")


@pytest.mark.subprocess
def test_the_committed_generated_code_matches_the_proto(tmp_path: Path) -> None:
    """Regenerated with the documented command, every generated file is the
    committed one."""
    command = [arg.replace("=.", f"={tmp_path}") for arg in GENERATE]
    subprocess.run([sys.executable, "-m", *command], cwd=ROOT, check=True)
    for folder in (MESSAGING, VALIDATE):
        for generated in sorted((ROOT / folder).glob("*_pb2*")):
            regenerated = tmp_path / folder / generated.name
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
def test_none_is_unspecified_and_never_sent(vocabulary: str) -> None:
    """None is 0, which implicit presence never sends; a number the enum does not
    name is refused by the contract (tests/hospital/test_messaging.py)."""
    from web.shared import vocabulary as words
    from web.shared.messaging import messages_pb2
    from web.shared.messaging.convert import to_proto

    choices = getattr(words, vocabulary)
    enum = getattr(messages_pb2, vocabulary)
    assert to_proto(None, enum) == 0
    # One proto value per member and UNSPECIFIED: nothing the vocabulary lacks.
    assert len(enum.DESCRIPTOR.values) == len(choices) + 1


@pytest.mark.parametrize(
    ("message", "field"),
    [
        ("LabReport", "report_id"),
        ("Acknowledgement", "report_ids"),
        ("FinalModel", "run_id"),
        ("NewFinalModelsRequest", "held_run_ids"),
    ],
)
def test_ids_are_unsigned_integers(message: str, field: str) -> None:
    """An ID is a number on the wire, so a malformed one cannot be sent at all."""
    from google.protobuf.descriptor import FieldDescriptor

    from web.shared.messaging import messages_pb2

    descriptor = getattr(messages_pb2, message).DESCRIPTOR.fields_by_name[field]
    assert descriptor.type == FieldDescriptor.TYPE_UINT64


# The one part a message may leave out: ferritin takes no clinical indication,
# and a CBC without one is not screened (features/hospital/screening.feature).
OPTIONAL = {"LabOrder.clinical_indication"}


def _messages() -> list[str]:
    from web.shared.messaging import messages_pb2

    return list(messages_pb2.DESCRIPTOR.message_types_by_name)


@pytest.mark.parametrize("message", _messages())
def test_every_part_of_every_message_is_required(message: str) -> None:
    """Every message is complete or refused: the contract itself requires each of
    its parts (protovalidate), so every receiver refuses one that left any out.
    Lists (repeated and map fields) may be empty."""
    import protovalidate

    from web.shared.messaging import messages_pb2

    kind = getattr(messages_pb2, message)
    missing = {
        f"{message}.{violation.proto.field.elements[0].field_name}"
        for violation in protovalidate.collect_violations(kind())
        if violation.proto.rule_id == "required" and violation.proto.field
    }
    parts = {
        f"{message}.{field.name}"
        for field in kind.DESCRIPTOR.fields
        if not field.is_repeated
    }
    assert missing == parts - OPTIONAL


@pytest.mark.parametrize(
    ("message", "field"),
    [
        ("LabOrder", "age"),
        ("LabReport", "ferritin_suggested"),
        ("FinalModel", "federated_auroc"),
    ],
)
def test_a_part_whose_zero_is_a_value_is_sent_when_zero(
    message: str, field: str
) -> None:
    """Age 0, no ferritin suggestion and an AUROC of 0 are values: sent, they
    are present, and only a part left out is missing."""
    from web.shared.messaging import messages_pb2

    assert getattr(messages_pb2, message).DESCRIPTOR.fields_by_name[field].has_presence
