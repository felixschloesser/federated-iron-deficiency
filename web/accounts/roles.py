"""A user's role follows from the record linked to them (spec §3, Agents)."""

import enum
from typing import assert_never

from django.contrib.auth.models import AbstractBaseUser, AnonymousUser
from django.urls import reverse


class Role(enum.Enum):
    GENERAL_PRACTITIONER = "general practitioner"
    LABORATORY_STAFF = "laboratory staff"
    LABORATORY_DIRECTOR = "laboratory director"
    DATA_SCIENTIST = "data scientist"

    def people(self) -> str:
        """The people of this role, as a sentence names them."""
        match self:
            case Role.GENERAL_PRACTITIONER:
                return "general practitioners"
            case Role.LABORATORY_STAFF:
                return "laboratory staff"
            case Role.LABORATORY_DIRECTOR:
                return "laboratory directors"
            case Role.DATA_SCIENTIST:
                return "data scientists"
            case _:
                assert_never(self)

    def start_url(self) -> str:
        """The page a user of this role lands on after logging in."""
        match self:
            case Role.GENERAL_PRACTITIONER:
                return reverse("practice:patients")
            case Role.LABORATORY_STAFF:
                return reverse("lab:to_analyse")
            case Role.LABORATORY_DIRECTOR:
                return reverse("deployment:models")
            case Role.DATA_SCIENTIST:
                return reverse("training:final_models")
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
            case Role.LABORATORY_STAFF:
                return [
                    {"url": reverse("lab:to_analyse"), "label": "To analyse"},
                    {"url": reverse("lab:analysed"), "label": "Analysed"},
                ]
            case Role.LABORATORY_DIRECTOR:
                return [
                    {"url": reverse("deployment:models"), "label": "Screening models"}
                ]
            case Role.DATA_SCIENTIST:
                return [
                    {"url": reverse("training:final_models"), "label": "Final models"}
                ]
            case _:
                assert_never(self)


def role_of(user: AbstractBaseUser | AnonymousUser | None) -> Role | None:
    """Return the user's role, or None for an account without one."""
    # RoleBackend loads the record with the user, so this costs no query.
    if hasattr(user, "general_practitioner"):
        return Role.GENERAL_PRACTITIONER
    if hasattr(user, "laboratory_staff_member"):
        return Role.LABORATORY_STAFF
    if hasattr(user, "laboratory_director"):
        return Role.LABORATORY_DIRECTOR
    if hasattr(user, "data_scientist"):
        return Role.DATA_SCIENTIST
    return None
