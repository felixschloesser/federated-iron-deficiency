from django.conf import settings
from django.http import HttpRequest


# Shown when the party's settings name none; never what it calls as, which only
# its settings say (web/shared/messaging/identity.py).
DEFAULT_NAME = "Demo"


def party(request: HttpRequest) -> dict[str, str]:
    """The party this web app belongs to (demo/README.md): its name, which only
    its own settings set, or the default; and its primary colour's theme."""
    theme = f"pico.{settings.PRIMARY_COLOUR}" if settings.PRIMARY_COLOUR else "pico"
    return {
        "party_name": settings.PRACTICE_NAME
        or settings.HOSPITAL_NAME
        or settings.STARTUP_NAME
        or DEFAULT_NAME,
        "party_stylesheet": f"css/vendor/pico-2.1.1/{theme}.min.css",
    }
