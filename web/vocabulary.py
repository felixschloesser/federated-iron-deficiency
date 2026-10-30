"""Terms both kinds of deployment use: the general practitioner's app and the
hospital (terms: docs/spec/requirements.md §1). No models, so either may import it."""

from typing import assert_never

from django.db import models


class RegisteredSex(models.TextChoices):
    FEMALE = "female", "Female"
    MALE = "male", "Male"


class Test(models.TextChoices):
    CBC = "cbc", "CBC"
    FERRITIN = "ferritin", "ferritin"

    def takes_indication(self) -> bool:
        """Whether an order for this test states a clinical indication."""
        match self:
            case Test.CBC:
                return True
            case Test.FERRITIN:
                return False
            case _:
                assert_never(self)


class ClinicalIndication(models.TextChoices):
    NON_SPECIFIC_COMPLAINT = "non_specific_complaint", "Non-specific complaint"
    OTHER = "other", "Other"
