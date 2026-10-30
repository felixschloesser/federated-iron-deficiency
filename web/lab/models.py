"""Laboratory staff and samples (terms: docs/spec/requirements.md §1)."""

from django.conf import settings
from django.db import models

from web.nhanes.models import FERRITIN
from web.vocabulary import ClinicalIndication, RegisteredSex, Test


class LaboratoryStaffMember(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="laboratory_staff_member",
    )
    name = models.CharField(max_length=100)

    def __str__(self) -> str:
        return self.name


class Sample(models.Model):
    """A tube, known by the sample ID on its label (R2)."""

    sample_id = models.CharField(max_length=20, unique=True)
    # Absent until the tube has arrived; a later test uses the stored sample.
    received_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return self.sample_id


class LabOrder(models.Model):
    """One test on a sample, as the lab order (DF1) said: no patient field (R14)."""

    sample = models.ForeignKey(
        Sample, on_delete=models.PROTECT, related_name="lab_orders"
    )
    test = models.CharField(max_length=8, choices=Test.choices)
    indication = models.CharField(
        max_length=22, choices=ClinicalIndication.choices, null=True, blank=True
    )
    registered_sex = models.CharField(max_length=6, choices=RegisteredSex.choices)
    age = models.PositiveSmallIntegerField()
    general_practitioner = models.CharField(max_length=100)
    ordered_at = models.DateTimeField()
    # Absent until the analyser has run.
    analysed_at = models.DateTimeField(null=True, blank=True)
    results = models.JSONField(null=True, blank=True)

    class Meta:
        constraints = (
            models.UniqueConstraint(
                fields=["sample", "test"], name="one_test_per_sample"
            ),
        )

    def __str__(self) -> str:
        return f"{self.sample.sample_id} {self.test}"

    @property
    def ferritin(self) -> float | None:
        """The ferritin result, or None if not measured (not analysed, or not in NHANES)."""
        value = (self.results or {}).get(FERRITIN)
        return None if value is None else float(value)
