"""The practice's patients, their samples, the tests ordered on them, and the
lab reports that come back (features/practice/ordering.feature,
features/practice/reports.feature)."""

from dataclasses import dataclass
from datetime import datetime

from django.core.exceptions import ValidationError
from django.db import models, transaction

from web.shared.vocabulary import ClinicalIndication, RegisteredSex, ResultName, Test

INDICATION_REQUIRED = "A CBC needs a clinical indication."
NOT_SUGGESTED = "Ferritin is ordered only beside a lab report suggesting it."
# The tests whose order must state a clinical indication.
TAKES_INDICATION = [test.value for test in Test if test.takes_indication()]


class LaboratoryQuerySet(models.QuerySet["Laboratory"]):
    def primary(self) -> "Laboratory | None":
        """The laboratory samples go to by default, or None if the practice has
        not named one."""
        return self.filter(primary=True).first()

    @transaction.atomic
    def add(self, *, name: str, address: str, primary: bool) -> "Laboratory":
        """Add a laboratory, or change the address of an existing one. With
        `primary`, it becomes the primary laboratory and any other stops being
        one."""
        if primary:
            self.exclude(name=name).filter(primary=True).update(primary=False)
        defaults: dict[str, object] = {"address": address}
        if primary:
            defaults["primary"] = True
        laboratory, _ = self.update_or_create(name=name, defaults=defaults)
        return laboratory


class Laboratory(models.Model):
    """A hospital's laboratory that the practice sends samples to."""

    name = models.CharField(max_length=100, unique=True)
    # host:port of the hospital's lab-order endpoint.
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
    """Subquery: whether the patient (OuterRef) has a lab report that suggests
    ferritin on a sample with no ferritin order yet."""
    return models.Exists(
        LabReport.objects.filter(
            order__sample__patient=models.OuterRef("pk"), ferritin_suggested=True
        ).exclude(order__sample__orders__test=Test.FERRITIN)
    )


class PatientQuerySet(models.QuerySet["Patient"]):
    def awaiting_ferritin(self) -> "PatientQuerySet":
        """Patients with a ferritin suggestion the doctor has not acted on yet."""
        return self.filter(_awaits_ferritin())

    def with_ferritin_suggested(self) -> "PatientQuerySet":
        """Annotate each patient with `ferritin_suggested`, which the patient list
        marks."""
        return self.annotate(ferritin_suggested=_awaits_ferritin())


class Patient(models.Model):
    name = models.CharField(max_length=100)
    registered_sex = models.CharField(max_length=6, choices=RegisteredSex.choices)
    age = models.PositiveSmallIntegerField()

    objects = PatientQuerySet.as_manager()

    def __str__(self) -> str:
        return self.name

    @transaction.atomic
    def collect_sample(self, *, now: datetime, laboratory: Laboratory) -> "Sample":
        """Record a blood sample collected from this patient for the chosen
        laboratory, under the next unused sample ID. Tests are ordered on the
        sample afterwards and go to the same laboratory."""
        sample_id = SampleId.objects.unused().order_by("pk").first()
        if sample_id is None:
            raise ValidationError(
                {
                    "sample_id": ValidationError(
                        "The practice has no sample ID left.",
                        code="no_sample_id",
                    )
                }
            )
        return Sample.objects.create(
            patient=self,
            sample_id=sample_id,
            collected_at=now,
            laboratory=laboratory,
        )


class SampleIdQuerySet(models.QuerySet["SampleId"]):
    def unused(self) -> "SampleIdQuerySet":
        """The sample IDs no sample has taken yet."""
        return self.filter(sample__isnull=True)


class SampleId(models.Model):
    """A sample ID from the practice's stock of labels; each is used by at most
    one sample. In the demo the labels carry NHANES participants' numbers, so
    the analyser stand-in measures the blood of the participant whose number
    the sample carries."""

    value = models.CharField(max_length=20, unique=True)

    objects = SampleIdQuerySet.as_manager()

    def __str__(self) -> str:
        return self.value


class Sample(models.Model):
    """Blood collected from a patient at the practice. Tests are ordered on it,
    and its sample ID goes on the label."""

    patient = models.ForeignKey(
        Patient, on_delete=models.PROTECT, related_name="samples"
    )
    sample_id = models.OneToOneField(
        SampleId, on_delete=models.PROTECT, related_name="sample"
    )
    collected_at = models.DateTimeField()
    # Where the sample was sent; every test on it goes to the same laboratory.
    laboratory = models.ForeignKey(
        Laboratory, on_delete=models.PROTECT, related_name="samples"
    )

    def __str__(self) -> str:
        return self.sample_id.value

    # The methods below loop over .all() instead of calling .filter(), so they
    # reuse the orders the page prefetched instead of querying again.
    def tests_to_order(self) -> list[Test]:
        """The tests not yet ordered on this sample. A test ordered on suspicion
        (ferritin) is left out: it is offered only beside the lab report that
        suggests it."""
        ordered = {order.test for order in self.orders.all()}
        return [
            test for test in Test if test not in ordered and not test.on_suspicion()
        ]

    @property
    def tests_display(self) -> str:
        """The tests ordered on this sample, comma-separated: "CBC, ferritin"."""
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
        """Order one test on this sample, copying the patient's registered sex
        and age into the order. This also orders a later test, such as ferritin
        beside a suggestion."""
        order = self._order(test=test, indication=indication, now=now)
        order.full_clean()
        order.save()
        return order

    def order_refusal(self, *, test: Test, now: datetime) -> ValidationError | None:
        """Why this test cannot be ordered on this sample, whatever the
        indication (the sample already has it, or ferritin without a
        suggestion), or None if it can. The order page asks before showing its
        form; place_order checks again."""
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
        """Build an unsaved order with the patient's registered sex and age."""
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
        """Orders whose lab order has not been sent yet: the laboratory has
        neither confirmed nor rejected it."""
        return self.filter(sent_at__isnull=True, rejected_at__isnull=True)


class Order(models.Model):
    sample = models.ForeignKey(Sample, on_delete=models.PROTECT, related_name="orders")
    test = models.CharField(max_length=8, choices=Test.choices)
    # None for a test that takes no clinical indication.
    indication = models.CharField(
        max_length=24, choices=ClinicalIndication.choices, null=True, blank=True
    )
    # Copied from the patient when ordering; this is all the laboratory learns
    # about the patient.
    registered_sex = models.CharField(max_length=6, choices=RegisteredSex.choices)
    age = models.PositiveSmallIntegerField()
    ordered_at = models.DateTimeField()
    # None until the hospital confirms it received the lab order; after that it
    # is not sent again.
    sent_at = models.DateTimeField(null=True, blank=True)
    # Set only if the laboratory rejected the lab order, together with its
    # reason; a rejected lab order is not sent again either.
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
            # A test that takes a clinical indication has one; any other has none.
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
        """Record that the laboratory rejected this order's lab order, and why.
        The order is kept and not sent again; to order the test again, the
        general practitioner collects a new sample."""
        self.rejected_at, self.reason_for_rejection = now, reason
        self.save(update_fields=["rejected_at", "reason_for_rejection"])

    def clean(self) -> None:
        """Allow ferritin only when a lab report on the same sample suggests it.
        The rule spans rows, so a database constraint cannot hold it."""
        suggested = self.sample.orders.filter(lab_report__ferritin_suggested=True)
        if Test(self.test).on_suspicion() and not suggested.exists():
            raise ValidationError(
                {"test": ValidationError(NOT_SUGGESTED, code="ferritin_not_suggested")}
            )

    @property
    def report(self) -> "LabReport | None":
        """The order's lab report, or None until it is fetched."""
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
        """The value without padding or trailing zeros: 7, 4.16, 10.7."""
        return f"{self.value:g}"


def results_named(results: object) -> None:
    """Validate a lab report's stored results: each key is a result name and
    each value a float."""
    items = results.items() if isinstance(results, dict) else []
    for name, value in items:
        if name not in ResultName.values:
            raise ValidationError("A result has no result name.", code="no_result_name")
        if not isinstance(value, float):
            raise ValidationError("A result has no value.", code="no_value")


class LabReport(models.Model):
    """A lab report fetched from the hospital: the results and whether ferritin
    is suggested. The practice learns nothing else about the screening."""

    order = models.OneToOneField(
        Order, on_delete=models.PROTECT, related_name="lab_report"
    )
    # Empty when the laboratory reported no values.
    results = models.JSONField(blank=True, validators=[results_named])
    ferritin_suggested = models.BooleanField(default=False)
    released_at = models.DateTimeField()
    fetched_at = models.DateTimeField()

    def ferritin_order_offered(self) -> bool:
        """Whether to offer a ferritin order: the lab report suggests ferritin and its
        sample has no ferritin order yet."""
        # .all() instead of .filter() reuses the orders the page prefetched.
        return self.ferritin_suggested and not any(
            order.test == Test.FERRITIN for order in self.order.sample.orders.all()
        )

    @property
    def comment(self) -> str:
        """The comment shown to the general practitioner when ferritin is
        suggested: where the suggestion comes from, and that it is not a
        diagnosis. Empty otherwise."""
        if not self.ferritin_suggested:
            return ""
        return (
            "Ferritin suggested by the hospital's screening of this CBC."
            " Likely iron deficiency; not a diagnosis."
        )

    @property
    def note(self) -> str:
        """The note under a screened test's report that has no suggestion. It
        reads the same whether ferritin was not suggested or the CBC was not
        screened, so the lack of a suggestion is not read as reassurance."""
        if self.ferritin_suggested or not Test(self.order.test).is_screened():
            return ""
        return "No ferritin suggestion. This does not rule out iron deficiency."

    def values(self) -> list[ResultValue]:
        """The measured values under NHANES's names and units, without
        interpretation; empty when the laboratory reported none."""
        return [
            ResultValue(name.value, name.label, name.unit(), self.results[name.value])
            for name in ResultName
            if name.value in self.results
        ]
