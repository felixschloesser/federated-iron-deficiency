from typing import Any, ClassVar

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponseBase
from django.shortcuts import redirect

from web.accounts.roles import Role, role_of


class RoleRequiredMixin(LoginRequiredMixin):
    """Lets in only users of `role`; others go to their own start page, told why."""

    role: ClassVar[Role]

    def dispatch(
        self, request: HttpRequest, *args: Any, **kwargs: Any
    ) -> HttpResponseBase:
        user = request.user
        if not user.is_authenticated:
            return self.handle_no_permission()
        role = role_of(user)
        if role is None:  # Cannot log in without a role; only if it was removed since
            raise PermissionDenied
        if role is not self.role:
            messages.error(request, f"That page is for {self.role.people()}.")
            return redirect(role.start_url())
        return super().dispatch(request, *args, **kwargs)
