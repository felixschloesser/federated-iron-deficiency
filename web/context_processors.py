from django.conf import settings
from django.http import HttpRequest


def party(request: HttpRequest) -> dict[str, str]:
    """The party this deployment belongs to (demo/README.md), and its colour theme."""
    theme = f"pico.{settings.PARTY_COLOUR}" if settings.PARTY_COLOUR else "pico"
    return {
        "party_name": settings.PARTY_NAME,
        "party_stylesheet": f"css/vendor/pico-2.1.1/{theme}.min.css",
    }
