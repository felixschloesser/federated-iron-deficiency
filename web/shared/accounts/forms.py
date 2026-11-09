from typing import Any

from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError

from web.shared.accounts.models import User
from web.shared.accounts.roles import role_of
from web.shared.forms import NamedLabels


class RoleAuthenticationForm(NamedLabels, AuthenticationForm):
    """Log in only accounts that have a role in this party's app."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # A submitted form is shown again only when it has errors, and then the
        # error summary takes focus (includes/form.html). HTML allows one
        # autofocus per page, so the username field gives it up.
        if self.is_bound:
            self.fields["username"].widget.attrs.pop("autofocus", None)

    def get_invalid_login_error(self) -> ValidationError:
        # Plain wording that, like Django's, does not say which of the two was wrong.
        return ValidationError("Wrong username or password.", code="invalid_login")

    def clean(self) -> dict[str, Any]:
        try:
            return super().clean()
        except ValidationError as error:
            # Mark both fields invalid, so Pico draws them as invalid, without
            # telling which one was wrong.
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
