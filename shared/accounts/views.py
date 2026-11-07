from typing import Any

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.views.generic import RedirectView

from shared.accounts.roles import role_of


class HomeView(LoginRequiredMixin, RedirectView):
    """Sends a logged-in user to the start page of their role."""

    def get_redirect_url(self, *args: Any, **kwargs: Any) -> str:
        role = role_of(self.request.user)
        if role is None:  # Only if the role was removed after logging in
            raise PermissionDenied
        return role.start_url()
