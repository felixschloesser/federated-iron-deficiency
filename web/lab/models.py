"""Laboratory staff and samples (terms: docs/spec/requirements.md §1)."""

from django.conf import settings
from django.db import models

from iron_deficiency.dataset import ELIGIBLE_AGES
from web.deployment.models import FinalModel
from web.lab.domain import NotScreened, ScreeningResult
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
    """A sample, known by the sample ID on its label and the general practitioner's
    app that sent it (R2, R24): two apps may use the same sample ID. It arrives
    with its lab order; a later test on it is measured on the stored sample."""

    # The common name of the app's client certificate, as the endpoint saw it.
    client = models.CharField(max_length=100)
    sample_id = models.CharField(max_length=20)

    class Meta:
        constraints = (
            models.UniqueConstraint(
                fields=["client", "sample_id"], name="one_sample_per_client"
            ),
        )

    def __str__(self) -> str:
        return self.sample_id


class LabOrder(models.Model):
    """One test on a sample, as the lab order (DF23) said: no patient field (R14)."""

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
    # Absent for ferritin, which is never screened (R12), and until analysed.
    screening_result = models.CharField(
        max_length=22, choices=ScreeningResult.choices, null=True, blank=True
    )
    # Present only when not screened (R5); no score is ever stored (R7).
    not_screened_reason = models.CharField(
        max_length=22, choices=NotScreened.choices, null=True, blank=True
    )
    # The final model that screened this CBC (R6); absent when not screened.
    screened_by = models.ForeignKey(
        FinalModel,
        on_delete=models.PROTECT,
        related_name="screening_results",
        null=True,
        blank=True,
    )
    # Absent until the general practitioner's app confirmed it has the lab report.
    report_acknowledged_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = (
            models.UniqueConstraint(
                fields=["sample", "test"], name="one_test_per_sample"
            ),
        )

    def __str__(self) -> str:
        return f"{self.sample.sample_id} {self.test}"

    def not_eligible(self) -> NotScreened | None:
        """The first condition R4 fails, in the order indication, sex, age."""
        if self.indication != ClinicalIndication.NON_SPECIFIC_COMPLAINT:
            return NotScreened.INDICATION
        if self.registered_sex != RegisteredSex.FEMALE:
            return NotScreened.SEX
        if not ELIGIBLE_AGES[0] <= self.age <= ELIGIBLE_AGES[1]:
            return NotScreened.AGE
        return None

    @property
    def ferritin_suggested(self) -> bool:
        """All the lab report says of screening (R9, R25)."""
        return self.screening_result == ScreeningResult.FERRITIN_SUGGESTED

    @property
    def ferritin(self) -> float | None:
        """The ferritin result, or None if not measured (not analysed, or not in NHANES)."""
        value = (self.results or {}).get(FERRITIN)
        return None if value is None else float(value)
