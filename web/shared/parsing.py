"""Parse another party's message with the receiver's own model fields: each value
becomes what its field stores, or the field's validation error refuses it."""

from collections.abc import Hashable, Iterable
from typing import Any

from django.core.exceptions import ValidationError
from django.db import models


def parsed(*parts: tuple[type[models.Model], dict[str, object]]) -> dict[str, Any]:
    """Clean each value with its model's field and return the cleaned values.

    Raises one ValidationError, keyed by field name, with every value a field
    refuses (codes such as null, blank, invalid_choice)."""
    values: dict[str, Any] = {}
    errors: dict[str, list[ValidationError]] = {}
    for model, fields in parts:
        for name, value in fields.items():
            try:
                field = model._meta.get_field(name)
                if not isinstance(field, models.Field):
                    raise TypeError(f"{model.__name__}.{name} is no field of its own.")
                values[name] = field.clean(value, None)
            except ValidationError as error:
                errors[name] = error.error_list
    if errors:
        raise ValidationError(errors)
    return values


def once_each(part: str, values: Iterable[Hashable], code: str) -> None:
    """Refuse a list that names the same thing twice, since the message would not
    say which of the two it meant. Raises ValidationError on `part` with `code`."""
    named = list(values)
    if len(set(named)) < len(named):
        raise ValidationError({part: ValidationError("Names one twice.", code=code)})
