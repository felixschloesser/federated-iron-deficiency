from django.conf import settings
from django.http import HttpRequest


def party(request: HttpRequest) -> dict[str, str | None]:
    """The party this web app belongs to (demo/README.md): its name, which only
    its own settings set, and its primary colour's theme."""
    theme = f"pico.{settings.PRIMARY_COLOUR}" if settings.PRIMARY_COLOUR else "pico"
    return {
        "party_name": settings.PRACTICE_NAME
        or settings.HOSPITAL_NAME
        or settings.STARTUP_NAME,
        "party_stylesheet": f"css/vendor/pico-2.1.1/{theme}.min.css",
    }
