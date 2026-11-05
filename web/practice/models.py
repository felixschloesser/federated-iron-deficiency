"""General practitioners, their patients, and orders (terms: glossary.toml)."""

from dataclasses import dataclass
from datetime import datetime

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction

from web.vocabulary import RESULT_NAMES, ClinicalIndication, RegisteredSex, Test

INDICATION_REQUIRED = "A CBC needs a clinical indication."
NOT_SUGGESTED = "Ferritin is ordered only beside a lab report suggesting it."
# The tests an order states a clinical indication for (Test.takes_indication).
TAKES_INDICATION = [test.value for test in Test if test.takes_indication()]


class LaboratoryQuerySet(models.QuerySet["Laboratory"]):
    def primary(self) -> "Laboratory | None":
        """The laboratory samples go to unless the general practitioner picks
        another; None while the practice has named none (R22)."""
        return self.filter(primary=True).first()

    @transaction.atomic
    def add(self, *, name: str, address: str, primary: bool) -> "Laboratory":
        """Add a laboratory or change its address; `primary` makes it the primary
        laboratory, in place of any other (R22)."""
        if primary:
            self.exclude(name=name).filter(primary=True).update(primary=False)
        defaults: dict[str, object] = {"address": address}
        if primary:
            defaults["primary"] = True
        laboratory, _ = self.update_or_create(name=name, defaults=defaults)
        return laboratory


class Laboratory(models.Model):
    """A hospital's laboratory the practice sends samples to (R22)."""

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


class GeneralPractitioner(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="general_practitioner",
    )
    name = models.CharField(max_length=100)

    class Meta:
        constraints = (
            # A practice has one general practitioner (R13): any second row
            # repeats the constant.
            models.UniqueConstraint(
                models.Value(1),
                name="one_general_practitioner",
                violation_error_code="one_general_practitioner",
                violation_error_message="A practice has one general practitioner.",
            ),
        )

    def __str__(self) -> str:
        return self.name

    @transaction.atomic
    def collect_sample(
        self,
        *,
        patient: "Patient",
        now: datetime,
        laboratory: Laboratory | None = None,
    ) -> "Sample":
        """Record blood collected from a patient of the practice, with the patient's
        next sample ID, for the laboratory chosen for it; tests are ordered on it
        afterwards and follow it there (R2, R22, R26)."""
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
            patient=patient,
            sample_id=patient.next_sample_id(),
            collected_at=now,
            laboratory=laboratory,
        )

    @transaction.atomic
    def place_order(
        self,
        *,
        sample: "Sample",
        test: Test,
        indication: ClinicalIndication | None,
        now: datetime,
    ) -> "Order":
        """Order one test on a collected sample, copying the patient's registered
        sex and age, also a later one such as ferritin beside a suggestion (R1, R2,
        R11, R14, R26)."""
        order = self._order(sample=sample, test=test, indication=indication, now=now)
        order.full_clean()
        order.save()
        return order

    def order_refusal(
        self, *, sample: "Sample", test: Test, now: datetime
    ) -> ValidationError | None:
        """What would refuse this test on this sample whatever its indication: a
        test the sample has (R26), ferritin without a suggestion (R11). The order
        page asks before showing its form; place_order checks it again."""
        order = self._order(sample=sample, test=test, indication=None, now=now)
        try:
            order.full_clean(exclude=["indication"])
        except ValidationError as refusal:
            return refusal
        return None

    def _order(
        self,
        *,
        sample: "Sample",
        test: Test,
        indication: ClinicalIndication | None,
        now: datetime,
    ) -> "Order":
        """The order as placed: the patient's registered sex and age copied (R1)."""
        return Order(
            sample=sample,
            test=test,
            indication=indication,
            registered_sex=sample.patient.registered_sex,
            age=sample.patient.age,
            ordered_at=now,
        )


def _awaits_ferritin() -> models.Exists:
    """Whether the outer patient has a lab report suggesting ferritin on a sample
    with no ferritin order yet (R11)."""
    return models.Exists(
        LabReport.objects.filter(
            order__sample__patient=models.OuterRef("pk"), ferritin_suggested=True
        ).exclude(order__sample__orders__test=Test.FERRITIN)
    )


class PatientQuerySet(models.QuerySet["Patient"]):
    def awaiting_ferritin(self) -> "PatientQuerySet":
        """The patients whose doctor has a ferritin suggestion to act on (R11)."""
        return self.filter(_awaits_ferritin())

    def with_ferritin_suggested(self) -> "PatientQuerySet":
        """Each patient with `ferritin_suggested`, for the patient list's mark."""
        return self.annotate(ferritin_suggested=_awaits_ferritin())


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

    objects = PatientQuerySet.as_manager()

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
    # Where the sample went, so every test on it goes there too (R2, R22); absent
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
        constraints = (
            # Each test at most once per sample (R26).
            models.UniqueConstraint(
                fields=["sample", "test"],
                name="one_order_per_sample_and_test",
                violation_error_code="already_ordered",
                violation_error_message="This sample already has this test.",
            ),
            # A clinical indication exactly for the tests that take one (R1).
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
        )

    def clean(self) -> None:
        """Ferritin only on suspicion: its sample has a lab report suggesting it
        (R11). Across rows, so no constraint can hold it."""
        suggested = self.sample.orders.filter(lab_report__ferritin_suggested=True)
        if Test(self.test).on_suspicion() and not suggested.exists():
            raise ValidationError(
                {"test": ValidationError(NOT_SUGGESTED, code="ferritin_not_suggested")}
            )

    @property
    def screened_indication(self) -> bool:
        """All the lab order says of the indication (R4, R25): whether it is a
        screened one. Which indication it is stays at the practice."""
        return (
            self.indication is not None
            and ClinicalIndication(self.indication).is_screened()
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

    def ferritin_order_offered(self) -> bool:
        """Order ferritin beside a suggestion, until its sample has ferritin (R11, R26)."""
        # .all(), not .filter(): uses the sample's orders when the page prefetched them.
        return self.ferritin_suggested and not any(
            order.test == Test.FERRITIN for order in self.order.sample.orders.all()
        )

    @property
    def comment(self) -> str:
        """The comment the general practitioner reads: only for a suggestion (R9),
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
        empty when NHANES has none (R3)."""
        return [
            ResultValue(variable, names.name, names.unit, self.results[variable])
            for variable, names in RESULT_NAMES.items()
            if variable in self.results
        ]
