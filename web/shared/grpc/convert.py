"""Convert the proto's enums and timestamps to and from web.shared.vocabulary
choices and datetimes.

A proto enum value is its vocabulary member's name with the enum's prefix, as the
protobuf style guide asks: Test.CBC is TEST_CBC. Value 0 (UNSPECIFIED) means none.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from django.db import models
from google.protobuf.timestamp_pb2 import Timestamp

if TYPE_CHECKING:
    # Exists only in types-protobuf: the generic base class of every generated enum.
    from google.protobuf.internal.enum_type_wrapper import _EnumTypeWrapper


def _prefix[Value: int](enum: _EnumTypeWrapper[Value]) -> str:
    """The enum's name in the values' style: RegisteredSex is REGISTERED_SEX."""
    return re.sub(r"(?<!^)(?=[A-Z])", "_", enum.DESCRIPTOR.name).upper()


def to_proto[Value: int](
    choice: models.TextChoices | None, enum: _EnumTypeWrapper[Value]
) -> Value:
    """Return the proto enum value for a vocabulary member, or UNSPECIFIED for None."""
    name = "UNSPECIFIED" if choice is None else choice.name
    return enum.Value(f"{_prefix(enum)}_{name}")


def from_proto[Value: int](
    value: Value, enum: _EnumTypeWrapper[Value], choices: type[models.TextChoices]
) -> str | None:
    """Return the vocabulary value a proto enum value names, for the receiver's
    model to parse, or None for UNSPECIFIED. A number the enum does not know is
    returned as that number, which matches no choice, so the model refuses it."""
    if value == 0:
        return None
    try:
        name = enum.Name(value)
    except ValueError:
        return str(value)
    return str(choices[name.removeprefix(f"{_prefix(enum)}_")])


def timestamp(moment: datetime) -> Timestamp:
    stamp = Timestamp()
    stamp.FromDatetime(moment)
    return stamp


def moment(stamp: Timestamp) -> datetime:
    return stamp.ToDatetime(tzinfo=UTC)
