"""General practitioners, their patients, and orders (terms: docs/spec/requirements.md §1)."""

from django.conf import settings
from django.db import models

from web.vocabulary import ClinicalIndication, RegisteredSex, Test


class GeneralPractitioner(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="general_practitioner",
    )
    name = models.CharField(max_length=100)

    def __str__(self) -> str:
        return self.name


class Patient(models.Model):
    general_practitioner = models.ForeignKey(
        GeneralPractitioner, on_delete=models.PROTECT, related_name="patients"
    )
    name = models.CharField(max_length=100)
    registered_sex = models.CharField(max_length=6, choices=RegisteredSex.choices)
    age = models.PositiveSmallIntegerField()
    # On the tube's label at the first order; in the demo the patient's NHANES
    # number, which the hospital's analyser stand-in looks up (spec §8).
    sample_id = models.CharField(max_length=20, unique=True)

    def __str__(self) -> str:
        return self.name


class OrderQuerySet(models.QuerySet["Order"]):
    def of_general_practitioner(
        self, general_practitioner: GeneralPractitioner
    ) -> "OrderQuerySet":
        """Only this general practitioner's orders (R13)."""
        return self.filter(patient__general_practitioner=general_practitioner)


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
    sample_id = models.CharField(max_length=20)
    ordered_at = models.DateTimeField()
    # Absent until the hospital confirmed the lab order (DF1); then never sent again.
    sent_at = models.DateTimeField(null=True, blank=True)

    objects = OrderQuerySet.as_manager()

    class Meta:
        # One sample per patient, each test at most once (R26).
        constraints = (
            models.UniqueConstraint(
                fields=["patient", "test"], name="one_test_per_patient"
            ),
        )


class LabReport(models.Model):
    """A lab report fetched from the hospital (DF20): results and the comment only."""

    order = models.OneToOneField(
        Order, on_delete=models.PROTECT, related_name="lab_report"
    )
    results = models.JSONField()
    comment = models.TextField(blank=True)
    released_at = models.DateTimeField()
    fetched_at = models.DateTimeField()
