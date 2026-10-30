from django.conf import settings
from django.http import HttpRequest


def party(request: HttpRequest) -> dict[str, str]:
    """The party this deployment belongs to (spec §9)."""
    return {"party_name": settings.PARTY_NAME}
