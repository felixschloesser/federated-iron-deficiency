"""A user's role follows from the record linked to them (spec §3, Agents)."""

import enum
from typing import assert_never

from django.contrib.auth.models import AbstractBaseUser, AnonymousUser
from django.urls import reverse


class Role(enum.Enum):
    GENERAL_PRACTITIONER = "general practitioner"

    def start_url(self) -> str:
        """The page a user of this role lands on after logging in."""
        match self:
            case Role.GENERAL_PRACTITIONER:
                return reverse("practice:patients")
            case _:
                assert_never(self)

    def nav_links(self) -> list[dict[str, str]]:
        """The pages of this role, linked from the header."""
        match self:
            case Role.GENERAL_PRACTITIONER:
                return [
                    {"url": reverse("practice:patients"), "label": "Patients"},
                    {"url": reverse("practice:orders"), "label": "Orders"},
                ]
            case _:
                assert_never(self)


def role_of(user: AbstractBaseUser | AnonymousUser | None) -> Role | None:
    """Return the user's role, or None for an account without one."""
    # RoleBackend loads the record with the user, so this costs no query.
    if hasattr(user, "general_practitioner"):
        return Role.GENERAL_PRACTITIONER
    return None
