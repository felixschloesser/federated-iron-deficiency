"""Mixins for the forms that the shared include includes/form.html renders."""

from typing import Any


class NamedLabels:
    """Render labels without Django's trailing colon: "Username", not "Username:"."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("label_suffix", "")
        super().__init__(*args, **kwargs)
