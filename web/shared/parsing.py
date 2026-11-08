"""Another party's message, parsed by the receiver's own model fields: each part
becomes the value its field stores, or the field's error refuses it."""

from typing import Any

from django.core.exceptions import ValidationError
from django.db import models


def parsed(*parts: tuple[type[models.Model], dict[str, object]]) -> dict[str, Any]:
    """Each part as its model's field parses it. Raises ValidationError, by part,
    for every part a field refuses (its code: null, blank, invalid_choice, …)."""
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
