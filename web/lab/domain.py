"""Screening results (R4, R5, R8; terms: docs/spec/requirements.md §1)."""

from django.db import models

from iron_deficiency.dataset import ELIGIBLE_AGES


class ScreeningResult(models.TextChoices):
    FERRITIN_SUGGESTED = "ferritin_suggested", "Ferritin suggested"
    FERRITIN_NOT_SUGGESTED = "ferritin_not_suggested", "Ferritin not suggested"
    NOT_SCREENED = "not_screened", "Not screened"


class NotScreened(models.TextChoices):
    """Why a CBC was not screened: the first failing condition (R5), else why
    there is no usable deployed model (web.deployment.domain.NoUsableModel)."""

    INDICATION = "indication", "not a non-specific complaint"
    SEX = "sex", "registered sex not female"
    AGE = "age", f"age outside {ELIGIBLE_AGES[0]}–{ELIGIBLE_AGES[1]}"
    NO_DEPLOYED_MODEL = "no_deployed_model", "no model deployed"
    DEPLOYED_MODEL_CHANGED = (
        "deployed_model_changed",
        "deployed model file changed",
    )
