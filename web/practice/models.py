"""General practitioners, their patients, and orders (terms: docs/spec/requirements.md §1)."""

from dataclasses import dataclass

from django.conf import settings
from django.db import models

from web.vocabulary import RESULT_NAMES, ClinicalIndication, RegisteredSex, Test


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
    # Demo only: the NHANES participant this patient is, which each of their
    # sample IDs starts with so the analyser stand-in can measure it (spec §8).
    nhanes_number = models.CharField(max_length=20, unique=True)

    def __str__(self) -> str:
        return self.name

    def next_sample_id(self) -> str:
        """The sample ID for this patient's next sample: 135318-1, 135318-2, …"""
        return f"{self.nhanes_number}-{self.samples.count() + 1}"


class Sample(models.Model):
    """Blood collected from a patient at the practice; its tests are ordered on
    it, and its sample ID goes on the label (R26)."""

    patient = models.ForeignKey(
        Patient, on_delete=models.PROTECT, related_name="samples"
    )
    sample_id = models.CharField(max_length=20, unique=True)
    collected_at = models.DateTimeField()

    def __str__(self) -> str:
        return self.sample_id


class OrderQuerySet(models.QuerySet["Order"]):
    def of_general_practitioner(
        self, general_practitioner: GeneralPractitioner
    ) -> "OrderQuerySet":
        """Only this general practitioner's orders (R13)."""
        return self.filter(sample__patient__general_practitioner=general_practitioner)


class Order(models.Model):
    sample = models.ForeignKey(Sample, on_delete=models.PROTECT, related_name="orders")
    test = models.CharField(max_length=8, choices=Test.choices)
    # Absent for a test that takes none (Test.takes_indication).
    indication = models.CharField(
        max_length=24, choices=ClinicalIndication.choices, null=True, blank=True
    )
    # Copied at ordering: all the lab learns about the patient (R1, R14).
    registered_sex = models.CharField(max_length=6, choices=RegisteredSex.choices)
    age = models.PositiveSmallIntegerField()
    ordered_at = models.DateTimeField()
    # Absent until the hospital confirmed the lab order (DF23); then never sent again.
    sent_at = models.DateTimeField(null=True, blank=True)

    objects = OrderQuerySet.as_manager()

    class Meta:
        # Each test at most once per sample (R26).
        constraints = (
            models.UniqueConstraint(
                fields=["sample", "test"], name="one_order_per_sample_and_test"
            ),
        )


@dataclass(frozen=True)
class ResultValue:
    variable: str
    name: str
    unit: str
    value: float

    @property
    def shown(self) -> str:
        """The value as measured, without a padded or trailing zero: 7, 4.16, 10.7."""
        return f"{self.value:g}"


class LabReport(models.Model):
    """A lab report fetched from the hospital (DF25): results, and whether
    ferritin is suggested; nothing else of screening (R9, R25)."""

    order = models.OneToOneField(
        Order, on_delete=models.PROTECT, related_name="lab_report"
    )
    results = models.JSONField()
    ferritin_suggested = models.BooleanField(default=False)
    released_at = models.DateTimeField()
    fetched_at = models.DateTimeField()

    @property
    def comment(self) -> str:
        """The comment the general practitioner reads: only for a suggestion (R9)."""
        return "Ferritin suggested." if self.ferritin_suggested else ""

    def values(self) -> list[ResultValue]:
        """The measured values under NHANES's names and units, uninterpreted;
        empty when NHANES has none (R3)."""
        return [
            ResultValue(variable, names.name, names.unit, self.results[variable])
            for variable, names in RESULT_NAMES.items()
            if variable in self.results
        ]
