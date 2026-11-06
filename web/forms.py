"""What every form rendered by the kit (web/templates/kit/form.html) shares."""

from typing import Any


class NamedLabels:
    """Labels name their field, "Username", not Django's prompt "Username:"."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("label_suffix", "")
        super().__init__(*args, **kwargs)
