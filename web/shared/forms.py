"""What every form rendered by the shared form include (web/shared/templates/includes/form.html) shares."""

from typing import Any


class NamedLabels:
    """Labels name their field, "Username", not Django's prompt "Username:"."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("label_suffix", "")
        super().__init__(*args, **kwargs)
