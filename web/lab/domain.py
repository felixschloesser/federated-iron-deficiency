"""Screening results (R4, R5, R8; terms: docs/spec/requirements.md §1)."""

from typing import assert_never

from django.db import models

from iron_deficiency.dataset import ELIGIBLE_AGES
from web.deployment.domain import NoUsableModel


class ScreeningResult(models.TextChoices):
    FERRITIN_SUGGESTED = "ferritin_suggested", "Ferritin suggested"
    FERRITIN_NOT_SUGGESTED = "ferritin_not_suggested", "Ferritin not suggested"
    NOT_SCREENED = "not_screened", "Not screened"


class NotScreened(models.TextChoices):
    """Why a CBC was not screened: the first failing condition (R5), else why
    there is no usable deployed model (web.deployment.domain.NoUsableModel)."""

    INDICATION = "indication", "clinical indication not screened"
    SEX = "sex", "registered sex not female"
    AGE = "age", f"age outside {ELIGIBLE_AGES[0]}–{ELIGIBLE_AGES[1]}"
    NO_DEPLOYED_MODEL = "no_deployed_model", "no screening model deployed"
    DEPLOYED_MODEL_CHANGED = (
        "deployed_model_changed",
        "deployed model file changed",
    )

    @classmethod
    def because(cls, no_usable_model: NoUsableModel) -> "NotScreened":
        match no_usable_model:
            case NoUsableModel.NO_DEPLOYED_MODEL:
                return cls.NO_DEPLOYED_MODEL
            case NoUsableModel.DEPLOYED_MODEL_CHANGED:
                return cls.DEPLOYED_MODEL_CHANGED
            case _:
                assert_never(no_usable_model)

    def is_model_problem(self) -> bool:
        """Whether the hospital's model, not the patient, kept the CBC unscreened."""
        match self:
            case NotScreened.INDICATION | NotScreened.SEX | NotScreened.AGE:
                return False
            case NotScreened.NO_DEPLOYED_MODEL | NotScreened.DEPLOYED_MODEL_CHANGED:
                return True
            case _:
                assert_never(self)
