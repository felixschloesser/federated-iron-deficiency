from django.contrib.auth.models import AbstractUser
from django.db import models

from web.shared.accounts.roles import Role


class User(AbstractUser):
    """Django's user with a role. A custom user model from the start, because
    Django cannot switch to one once migrations exist."""

    role = models.CharField(max_length=20, choices=Role.choices, null=True, blank=True)

    class Meta(AbstractUser.Meta):
        constraints = (
            models.UniqueConstraint(
                fields=["role"],
                condition=models.Q(role=Role.GENERAL_PRACTITIONER),
                name="one_general_practitioner",
                violation_error_code="one_general_practitioner",
                violation_error_message="A practice has one general practitioner.",
            ),
            models.UniqueConstraint(
                fields=["role"],
                condition=models.Q(role=Role.LABORATORY_DIRECTOR),
                name="one_laboratory_director",
                violation_error_code="one_laboratory_director",
                violation_error_message="A hospital has one laboratory director.",
            ),
        )
