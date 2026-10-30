"""Screening results (R4, R5, R8; terms: docs/spec/requirements.md §1)."""

from django.db import models


class ScreeningResult(models.TextChoices):
    FERRITIN_SUGGESTED = "ferritin_suggested", "Ferritin suggested"
    FERRITIN_NOT_SUGGESTED = "ferritin_not_suggested", "Ferritin not suggested"
    NOT_SCREENED = "not_screened", "Not screened"


class NotScreened(models.TextChoices):
    """Why a CBC was not screened: the first failing condition (R5), else why
    there is no usable deployed model (web.deployment.domain.NoUsableModel)."""

    INDICATION = "indication", "clinical indication"
    SEX = "sex", "registered sex"
    AGE = "age", "age"
    NO_DEPLOYED_MODEL = "no_deployed_model", "no final model is deployed"
    DEPLOYED_MODEL_CHANGED = (
        "deployed_model_changed",
        "the deployed model changed on disk",
    )
