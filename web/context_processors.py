from django.conf import settings
from django.http import HttpRequest


def hospital(request: HttpRequest) -> dict[str, str]:
    """The hospital this deployment belongs to (spec §9)."""
    return {"hospital_name": settings.HOSPITAL_NAME}
