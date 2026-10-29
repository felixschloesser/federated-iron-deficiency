from typing import Any

from django.conf import settings
from django.http import HttpRequest, HttpResponseServerError
from django.template.loader import render_to_string
from django.views import View


class ServerErrorView(View):
    """500.html with the hospital's name; reads settings only, never the database."""

    def dispatch(
        self, request: HttpRequest, *args: Any, **kwargs: Any
    ) -> HttpResponseServerError:
        context = {"hospital_name": settings.HOSPITAL_NAME}
        return HttpResponseServerError(render_to_string("500.html", context))
