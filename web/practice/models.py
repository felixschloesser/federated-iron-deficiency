"""GPs, their patients, and orders (terms: docs/spec/requirements.md §1)."""

from typing import assert_never

from django.conf import settings
from django.db import models


class RegisteredSex(models.TextChoices):
    FEMALE = "female", "Female"
    MALE = "male", "Male"


class Test(models.TextChoices):
    CBC = "cbc", "CBC"
    FERRITIN = "ferritin", "Ferritin"

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


class GP(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="gp"
    )
    name = models.CharField(max_length=100)

    def __str__(self) -> str:
        return self.name


class Patient(models.Model):
    gp = models.ForeignKey(GP, on_delete=models.PROTECT, related_name="patients")
    name = models.CharField(max_length=100)
    registered_sex = models.CharField(max_length=6, choices=RegisteredSex.choices)
    age = models.PositiveSmallIntegerField()

    def __str__(self) -> str:
        return self.name


class Order(models.Model):
    patient = models.ForeignKey(
        Patient, on_delete=models.PROTECT, related_name="orders"
    )
    test = models.CharField(max_length=8, choices=Test.choices)
    # Absent for a test that takes none (Test.takes_indication).
    indication = models.CharField(
        max_length=22, choices=ClinicalIndication.choices, null=True, blank=True
    )
    # Copied at ordering: all the lab learns about the patient (R1, R14).
    registered_sex = models.CharField(max_length=6, choices=RegisteredSex.choices)
    age = models.PositiveSmallIntegerField()
    ordered_at = models.DateTimeField()
