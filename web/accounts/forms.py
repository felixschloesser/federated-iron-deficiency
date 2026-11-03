from typing import Any

from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError

from web.accounts.models import User
from web.accounts.roles import role_of


class RoleAuthenticationForm(AuthenticationForm):
    """Lets in only accounts that have a role in this app."""

    def clean(self) -> dict[str, Any]:
        try:
            return super().clean()
        except ValidationError as error:
            # A wrong username or password: both fields, as Pico draws invalid ones,
            # without telling which was wrong.
            if error.code == "invalid_login":
                for name in ("username", "password"):
                    self.fields[name].widget.attrs["aria-invalid"] = "true"
            raise

    def confirm_login_allowed(self, user: User) -> None:
        super().confirm_login_allowed(user)
        if role_of(user) is None:
            raise ValidationError(
                "Your account has no role in this app. Ask the administrator.",
                code="no_role",
            )
