"""The roles a user may have; a user without one cannot log in."""

from typing import assert_never

from django.contrib.auth.models import AbstractBaseUser, AnonymousUser
from django.db import models
from django.urls import reverse


class Role(models.TextChoices):
    GENERAL_PRACTITIONER = "general_practitioner", "general practitioner"
    LABORATORY_STAFF = "laboratory_staff", "laboratory staff"
    LABORATORY_DIRECTOR = "laboratory_director", "laboratory director"
    DATA_SCIENTIST = "data_scientist", "data scientist"

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
                return reverse("lab:test_requests")
            case Role.LABORATORY_DIRECTOR:
                return reverse("deployment:screening_models")
            case Role.DATA_SCIENTIST:
                return reverse("training:runs")
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
                    {"url": reverse("lab:test_requests"), "label": "To analyse"},
                    {"url": reverse("lab:analysed"), "label": "Analysed"},
                ]
            case Role.LABORATORY_DIRECTOR:
                return [
                    {
                        "url": reverse("deployment:screening_models"),
                        "label": "Screening models",
                    },
                    {
                        "url": reverse("cohort:training_cohort"),
                        "label": "Training cohort",
                    },
                ]
            case Role.DATA_SCIENTIST:
                return [
                    {"url": reverse("training:runs"), "label": "Training runs"},
                    {"url": reverse("training:models"), "label": "Final models"},
                ]
            case _:
                assert_never(self)


def role_of(user: AbstractBaseUser | AnonymousUser | None) -> Role | None:
    """Return the user's role, or None for an account without one."""
    role = getattr(user, "role", None)
    return None if role is None else Role(role)
