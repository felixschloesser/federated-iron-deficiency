"""Laboratory staff and samples (terms: docs/spec/requirements.md §1)."""

from django.conf import settings
from django.db import models

from web.nhanes.models import FERRITIN


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
    order = models.OneToOneField(
        "practice.Order", on_delete=models.PROTECT, related_name="sample"
    )
    # Assigned by the laboratory on receipt (WHO LQMS 5-4, p. 66).
    sample_id = models.CharField(max_length=20, unique=True)
    received_at = models.DateTimeField()
    # Absent until the analyser has run.
    analysed_at = models.DateTimeField(null=True, blank=True)
    results = models.JSONField(null=True, blank=True)

    def __str__(self) -> str:
        return self.sample_id

    @property
    def ferritin(self) -> float | None:
        """The ferritin result, or None if not measured (not analysed, or not in NHANES)."""
        value = (self.results or {}).get(FERRITIN)
        return None if value is None else float(value)
