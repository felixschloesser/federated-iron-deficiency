"""The contract's enums and times, to and from web.shared.vocabulary and datetimes (web/shared/messaging/messages.proto).

A proto enum value is named after its vocabulary member with the enum's prefix, as
the proto style guide asks: Test.CBC is TEST_CBC. Value 0, UNSPECIFIED, is none.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from django.db import models
from google.protobuf.timestamp_pb2 import Timestamp

if TYPE_CHECKING:
    # Only in types-protobuf: the generic base of each generated enum.
    from google.protobuf.internal.enum_type_wrapper import _EnumTypeWrapper


def _prefix[Value: int](enum: _EnumTypeWrapper[Value]) -> str:
    """The enum's name in the values' style: RegisteredSex is REGISTERED_SEX."""
    return re.sub(r"(?<!^)(?=[A-Z])", "_", enum.DESCRIPTOR.name).upper()


def to_proto[Value: int](
    choice: models.TextChoices | None, enum: _EnumTypeWrapper[Value]
) -> Value:
    """The proto enum value of a vocabulary member; UNSPECIFIED for none."""
    name = "UNSPECIFIED" if choice is None else choice.name
    return enum.Value(f"{_prefix(enum)}_{name}")


def from_proto[Value: int, Choices: models.TextChoices](
    value: Value, enum: _EnumTypeWrapper[Value], choices: type[Choices]
) -> Choices:
    """The vocabulary member of a proto enum value. Only a receiver's parser calls
    it, on a message that passed the contract's validation, which takes only the
    values the enum names; never UNSPECIFIED, which is none and never sent."""
    return choices[enum.Name(value).removeprefix(f"{_prefix(enum)}_")]


def timestamp(moment: datetime) -> Timestamp:
    stamp = Timestamp()
    stamp.FromDatetime(moment)
    return stamp


def moment(stamp: Timestamp) -> datetime:
    return stamp.ToDatetime(tzinfo=UTC)
