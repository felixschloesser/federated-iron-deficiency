from typing import Any

from django.http import HttpRequest, HttpResponseServerError
from django.template.loader import render_to_string
from django.views import View

from web.context_processors import party


class ServerErrorView(View):
    """500.html with the party's name and colour; reads settings only, never the
    database."""

    def dispatch(
        self, request: HttpRequest, *args: Any, **kwargs: Any
    ) -> HttpResponseServerError:
        return HttpResponseServerError(render_to_string("500.html", party(request)))
