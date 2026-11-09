from typing import Any, ClassVar

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponseBase
from django.shortcuts import redirect

from web.shared.accounts.roles import Role, role_of


class RoleRequiredMixin(LoginRequiredMixin):
    """Let in only users with `role`; send anyone else to their own start page with
    a message saying why."""

    role: ClassVar[Role]

    def dispatch(
        self, request: HttpRequest, *args: Any, **kwargs: Any
    ) -> HttpResponseBase:
        user = request.user
        if not user.is_authenticated:
            return self.handle_no_permission()
        role = role_of(user)
        # Logging in requires a role here, so this happens only if the role was
        # removed after the user logged in.
        if role is None:
            raise PermissionDenied
        if role is not self.role:
            messages.error(request, f"That page is for {self.role.people()}.")
            return redirect(role.start_url())
        return super().dispatch(request, *args, **kwargs)
