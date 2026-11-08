"""General practitioners, their patients, and orders (terms: glossary.toml)."""

from dataclasses import dataclass
from datetime import datetime

from django.core.exceptions import ValidationError
from django.db import models, transaction

from web.shared.vocabulary import RESULT_NAMES, ClinicalIndication, RegisteredSex, Test

INDICATION_REQUIRED = "A CBC needs a clinical indication."
NOT_SUGGESTED = "Ferritin is ordered only beside a lab report suggesting it."
# The tests an order states a clinical indication for (Test.takes_indication).
TAKES_INDICATION = [test.value for test in Test if test.takes_indication()]


class LaboratoryQuerySet(models.QuerySet["Laboratory"]):
    def primary(self) -> "Laboratory | None":
        """The laboratory samples go to unless the general practitioner picks
        another; None while the practice has named none."""
        return self.filter(primary=True).first()

    @transaction.atomic
    def add(self, *, name: str, address: str, primary: bool) -> "Laboratory":
        """Add a laboratory or change its address; `primary` makes it the primary
        laboratory, in place of any other."""
        if primary:
            self.exclude(name=name).filter(primary=True).update(primary=False)
        defaults: dict[str, object] = {"address": address}
        if primary:
            defaults["primary"] = True
        laboratory, _ = self.update_or_create(name=name, defaults=defaults)
        return laboratory


class Laboratory(models.Model):
    """A hospital's laboratory the practice sends samples to (features/practice/ordering.feature)."""

    name = models.CharField(max_length=100, unique=True)
    # host:port of the hospital's messaging endpoint.
    address = models.CharField(max_length=200)
    primary = models.BooleanField(default=False)

    objects = LaboratoryQuerySet.as_manager()

    class Meta:
        constraints = (
            models.UniqueConstraint(
                fields=["primary"],
                condition=models.Q(primary=True),
                name="one_primary_laboratory",
                violation_error_code="one_primary_laboratory",
                violation_error_message="A practice has one primary laboratory.",
            ),
        )

    def __str__(self) -> str:
        return self.name


def _awaits_ferritin() -> models.Exists:
    """Whether the outer patient has a lab report suggesting ferritin on a sample
    with no ferritin order yet."""
    return models.Exists(
        LabReport.objects.filter(
            order__sample__patient=models.OuterRef("pk"), ferritin_suggested=True
        ).exclude(order__sample__orders__test=Test.FERRITIN)
    )


class PatientQuerySet(models.QuerySet["Patient"]):
    def awaiting_ferritin(self) -> "PatientQuerySet":
        """The patients whose doctor has a ferritin suggestion to act on."""
        return self.filter(_awaits_ferritin())

    def with_ferritin_suggested(self) -> "PatientQuerySet":
        """Each patient with `ferritin_suggested`, for the patient list's mark."""
        return self.annotate(ferritin_suggested=_awaits_ferritin())


class Patient(models.Model):
    name = models.CharField(max_length=100)
    registered_sex = models.CharField(max_length=6, choices=RegisteredSex.choices)
    age = models.PositiveSmallIntegerField()
    # Demo only: the NHANES participant this patient is, which each of their
    # sample IDs starts with so the analyser stand-in can measure it.
    nhanes_number = models.CharField(max_length=20, unique=True)

    objects = PatientQuerySet.as_manager()

    def __str__(self) -> str:
        return self.name

    def next_sample_id(self) -> str:
        """The sample ID for this patient's next sample: 135318-1, 135318-2, …"""
        return f"{self.nhanes_number}-{self.samples.count() + 1}"

    @transaction.atomic
    def collect_sample(
        self, *, now: datetime, laboratory: Laboratory | None = None
    ) -> "Sample":
        """Record blood collected from this patient, with their next sample ID,
        for the laboratory chosen for it; tests are ordered on it afterwards and follow it there."""
        if laboratory is None and Laboratory.objects.exists():
            raise ValidationError(
                {
                    "laboratory": ValidationError(
                        "Choose the laboratory the sample goes to.",
                        code="laboratory_required",
                    )
                }
            )
        return Sample.objects.create(
            patient=self,
            sample_id=self.next_sample_id(),
            collected_at=now,
            laboratory=laboratory,
        )


class Sample(models.Model):
    """Blood collected from a patient at the practice; its tests are ordered on
    it, and its sample ID goes on the label (features/practice/ordering.feature)."""

    patient = models.ForeignKey(
        Patient, on_delete=models.PROTECT, related_name="samples"
    )
    sample_id = models.CharField(max_length=20, unique=True)
    collected_at = models.DateTimeField()
    # Where the sample went, so every test on it goes there too; absent
    # only at a practice with no laboratory, as in development.
    laboratory = models.ForeignKey(
        Laboratory,
        on_delete=models.PROTECT,
        related_name="samples",
        null=True,
        blank=True,
    )

    def __str__(self) -> str:
        return self.sample_id

    # .all(), not .filter(), below: they use the orders when the page prefetched them.
    def tests_to_order(self) -> list[Test]:
        """The tests this sample does not have yet, but not one ordered on
        suspicion: that one is offered only beside the lab report suggesting it."""
        ordered = {order.test for order in self.orders.all()}
        return [
            test for test in Test if test not in ordered and not test.on_suspicion()
        ]

    @property
    def tests_display(self) -> str:
        """The tests ordered on it, in the order the queryset gives: "CBC, ferritin"."""
        return ", ".join(order.get_test_display() for order in self.orders.all())

    @property
    def lab_order_rejected(self) -> bool:
        """Whether the laboratory rejected a lab order on this sample."""
        return any(order.rejected_at is not None for order in self.orders.all())

    @property
    def ferritin_suggested(self) -> bool:
        """Whether a lab report on this sample suggests ferritin."""
        return any(
            order.report is not None and order.report.ferritin_suggested
            for order in self.orders.all()
        )

    @transaction.atomic
    def place_order(
        self,
        *,
        test: Test,
        indication: ClinicalIndication | None,
        now: datetime,
    ) -> "Order":
        """Order one test on this sample, copying the patient's registered
        sex and age, also a later one such as ferritin beside a suggestion."""
        order = self._order(test=test, indication=indication, now=now)
        order.full_clean()
        order.save()
        return order

    def order_refusal(self, *, test: Test, now: datetime) -> ValidationError | None:
        """What would refuse this test on this sample whatever its indication: a
        test the sample has, ferritin without a suggestion. The order
        page asks before showing its form; place_order checks it again."""
        order = self._order(test=test, indication=None, now=now)
        try:
            order.full_clean(exclude=["indication"])
        except ValidationError as refusal:
            return refusal
        return None

    def _order(
        self,
        *,
        test: Test,
        indication: ClinicalIndication | None,
        now: datetime,
    ) -> "Order":
        """The order as placed: the patient's registered sex and age copied."""
        return Order(
            sample=self,
            test=test,
            indication=indication,
            registered_sex=self.patient.registered_sex,
            age=self.patient.age,
            ordered_at=now,
        )


class OrderQuerySet(models.QuerySet["Order"]):
    def not_sent(self) -> "OrderQuerySet":
        """The orders whose lab order still waits to be sent: neither confirmed by
        the laboratory nor rejected by it."""
        return self.filter(sent_at__isnull=True, rejected_at__isnull=True)


class Order(models.Model):
    sample = models.ForeignKey(Sample, on_delete=models.PROTECT, related_name="orders")
    test = models.CharField(max_length=8, choices=Test.choices)
    # Absent for a test that takes none (Test.takes_indication).
    indication = models.CharField(
        max_length=24, choices=ClinicalIndication.choices, null=True, blank=True
    )
    # Copied at ordering: all the lab learns about the patient.
    registered_sex = models.CharField(max_length=6, choices=RegisteredSex.choices)
    age = models.PositiveSmallIntegerField()
    ordered_at = models.DateTimeField()
    # Absent until the hospital confirmed the lab order (DF23); then never sent again.
    sent_at = models.DateTimeField(null=True, blank=True)
    # Absent unless the laboratory rejected the lab order, with its reason for
    # rejection (glossary.toml, rejection); then never sent again either.
    rejected_at = models.DateTimeField(null=True, blank=True)
    reason_for_rejection = models.TextField(null=True, blank=True)

    objects = OrderQuerySet.as_manager()

    class Meta:
        constraints = (
            # Each test at most once per sample.
            models.UniqueConstraint(
                fields=["sample", "test"],
                name="one_order_per_sample_and_test",
                violation_error_code="already_ordered",
                violation_error_message="This sample already has this test.",
            ),
            # A clinical indication exactly for the tests that take one.
            models.CheckConstraint(
                condition=~models.Q(test__in=TAKES_INDICATION)
                | models.Q(indication__isnull=False),
                name="indication_required",
                violation_error_code="indication_required",
                violation_error_message=INDICATION_REQUIRED,
            ),
            models.CheckConstraint(
                condition=models.Q(test__in=TAKES_INDICATION)
                | models.Q(indication__isnull=True),
                name="indication_not_applicable",
                violation_error_code="indication_not_applicable",
                violation_error_message="Ferritin takes no clinical indication.",
            ),
            # A rejection is recorded with its reason, or not at all.
            models.CheckConstraint(
                condition=models.Q(
                    rejected_at__isnull=True, reason_for_rejection__isnull=True
                )
                | models.Q(
                    rejected_at__isnull=False, reason_for_rejection__isnull=False
                ),
                name="rejected_with_reason",
                violation_error_code="rejected_with_reason",
                violation_error_message="A rejection records when and why.",
            ),
        )

    @transaction.atomic
    def reject(self, *, reason: str, now: datetime) -> None:
        """The laboratory rejected its lab order, for `reason`: kept, never sent
        again; the general practitioner collects a new sample to order again."""
        self.rejected_at, self.reason_for_rejection = now, reason
        self.save(update_fields=["rejected_at", "reason_for_rejection"])

    def clean(self) -> None:
        """Ferritin only on suspicion: its sample has a lab report suggesting it. Across rows, so no constraint can hold it."""
        suggested = self.sample.orders.filter(lab_report__ferritin_suggested=True)
        if Test(self.test).on_suspicion() and not suggested.exists():
            raise ValidationError(
                {"test": ValidationError(NOT_SUGGESTED, code="ferritin_not_suggested")}
            )

    @property
    def report(self) -> "LabReport | None":
        """Its lab report, once fetched; None before."""
        report: LabReport | None = getattr(self, "lab_report", None)
        return report


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
    ferritin is suggested; nothing else of screening (features/practice/reports.feature)."""

    order = models.OneToOneField(
        Order, on_delete=models.PROTECT, related_name="lab_report"
    )
    results = models.JSONField()
    ferritin_suggested = models.BooleanField(default=False)
    released_at = models.DateTimeField()
    fetched_at = models.DateTimeField()

    def ferritin_order_offered(self) -> bool:
        """Order ferritin beside a suggestion, until its sample has ferritin."""
        # .all(), not .filter(): uses the sample's orders when the page prefetched them.
        return self.ferritin_suggested and not any(
            order.test == Test.FERRITIN for order in self.order.sample.orders.all()
        )

    @property
    def comment(self) -> str:
        """The comment the general practitioner reads: only for a suggestion,
        saying where it comes from and that it is no diagnosis."""
        if not self.ferritin_suggested:
            return ""
        return (
            "Ferritin suggested by the hospital's screening of this CBC."
            " Likely iron deficiency; not a diagnosis."
        )

    @property
    def note(self) -> str:
        """Under a screened test's report without a suggestion: the same words
        whether it was not suggested or not screened, so silence reassures no one."""
        if self.ferritin_suggested or not Test(self.order.test).is_screened():
            return ""
        return "No ferritin suggestion. This does not rule out iron deficiency."

    def values(self) -> list[ResultValue]:
        """The measured values under NHANES's names and units, uninterpreted;
        empty when NHANES has none."""
        return [
            ResultValue(variable, names.name, names.unit, self.results[variable])
            for variable, names in RESULT_NAMES.items()
            if variable in self.results
        ]
