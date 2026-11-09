from django.conf import settings
from django.http import HttpRequest


def party(request: HttpRequest) -> dict[str, str]:
    """Give every page the party's name and the stylesheet in its primary colour."""
    theme = f"pico.{settings.PRIMARY_COLOUR}" if settings.PRIMARY_COLOUR else "pico"
    return {
        "party_name": settings.PARTY_NAME,
        "party_stylesheet": f"css/vendor/pico-2.1.1/{theme}.min.css",
    }
