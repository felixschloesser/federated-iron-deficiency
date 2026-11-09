from typing import Any

from django.http import HttpRequest, HttpResponseServerError
from django.template.loader import render_to_string
from django.views import View

from web.shared.context_processors import party


class ServerErrorView(View):
    """Render 500.html with the party's name and colour. It reads only settings,
    never the database, so it still works when the database is what failed."""

    def dispatch(
        self, request: HttpRequest, *args: Any, **kwargs: Any
    ) -> HttpResponseServerError:
        return HttpResponseServerError(render_to_string("500.html", party(request)))
