"""The hospital's samples and the practices it works with (terms: glossary.toml)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TypedDict, assert_never

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Exists, OuterRef
from django_stubs_ext import WithAnnotations

from ml.cohort import ELIGIBLE_AGES, ELIGIBLE_SEX
from web.hospital.deployment.models import Deployment, NoUsableModel, ScreeningModel
from web.hospital.nhanes.models import Participant
from web.vocabulary import RegisteredSex, Test


class ScreeningResult(models.TextChoices):
    FERRITIN_SUGGESTED = "ferritin_suggested", "Ferritin suggested"
    FERRITIN_NOT_SUGGESTED = "ferritin_not_suggested", "Ferritin not suggested"
    NOT_SCREENED = "not_screened", "Not screened"


class NotScreened(models.TextChoices):
    """Why a CBC was not screened (features/screening.feature): the patient is not eligible, never which
    fact excluded them, or there is no usable deployed model
    (web.hospital.deployment.models.NoUsableModel), which lab staff act on (features/screening.feature)."""

    NOT_ELIGIBLE = "not_eligible", "not eligible"
    NO_DEPLOYED_MODEL = "no_deployed_model", "no screening model deployed"
    DEPLOYED_MODEL_CHANGED = (
        "deployed_model_changed",
        "deployed model file changed",
    )

    @classmethod
    def because(cls, no_usable_model: NoUsableModel) -> NotScreened:
        match no_usable_model:
            case NoUsableModel.NO_DEPLOYED_MODEL:
                return cls.NO_DEPLOYED_MODEL
            case NoUsableModel.DEPLOYED_MODEL_CHANGED:
                return cls.DEPLOYED_MODEL_CHANGED
            case _:
                assert_never(no_usable_model)

    def is_model_problem(self) -> bool:
        """Whether the hospital's model, not the patient, kept the CBC unscreened."""
        match self:
            case NotScreened.NOT_ELIGIBLE:
                return False
            case NotScreened.NO_DEPLOYED_MODEL | NotScreened.DEPLOYED_MODEL_CHANGED:
                return True
            case _:
                assert_never(self)


class PracticeManager(models.Manager["Practice"]):
    @transaction.atomic
    def add(self, *, certificate_name: str, name: str) -> Practice:
        """Register a practice the hospital works with, or change its name
        (features/messaging.feature)."""
        practice, _ = self.update_or_create(
            certificate_name=certificate_name, defaults={"name": name}
        )
        return practice


class Practice(models.Model):
    """A practice the hospital works with, by the certificate name the hospital
    issued it (glossary.toml): the lab's key for it, which the practice's app
    sends in every message. With the report's mutual TLS it would come from the
    practice's certificate instead; the demo leaves that out."""

    certificate_name = models.SlugField(max_length=100, unique=True)
    # As the hospital knows the practice; never sent.
    name = models.CharField(max_length=100)

    objects = PracticeManager()

    def __str__(self) -> str:
        return self.name


class Sample(models.Model):
    """A sample, known by the sample ID on its label and the practice that sent it
    (features/lab.feature, features/messaging.feature): two practices may use the same sample ID. It arrives with its lab
    order; a later test on it is measured on the stored sample."""

    practice = models.ForeignKey(
        Practice, on_delete=models.PROTECT, related_name="samples"
    )
    sample_id = models.CharField(max_length=20)

    class Meta:
        constraints = (
            models.UniqueConstraint(
                fields=["practice", "sample_id"], name="one_sample_per_practice"
            ),
        )

    def __str__(self) -> str:
        return self.sample_id


@dataclass(frozen=True)
class LabOrderDetails:
    """What a lab order (DF23) says: no patient name, no values (features/messaging.feature)."""

    sample_id: str
    test: Test
    # Whether the indication is a screened one (features/screening.feature); never which indication.
    screened_indication: bool
    registered_sex: RegisteredSex
    age: int
    ordered_at: datetime


class StoredSample(TypedDict):
    stored_sample: bool


class LabOrderManager(models.Manager["LabOrder"]):
    """What laboratory staff see: lab orders, which hold no patient field (features/access.feature)."""

    def to_analyse(self) -> models.QuerySet[WithAnnotations[LabOrder, StoredSample]]:
        """Tests the analyser has not run yet. A sample arrives with its lab order; it
        is a stored sample once another test on it has been analysed (features/lab.feature)."""
        analysed_on_same_sample = LabOrder.objects.filter(
            sample=OuterRef("sample"), analysed_at__isnull=False
        )
        return (
            self.filter(analysed_at__isnull=True)
            .annotate(stored_sample=Exists(analysed_on_same_sample))
            .select_related("sample")
            .order_by("ordered_at", "pk")
        )

    def analysed(self) -> models.QuerySet[LabOrder]:
        """Tests with results, newest first."""
        return (
            self.filter(analysed_at__isnull=False)
            .select_related("sample")
            .order_by("-analysed_at", "-pk")
        )

    def reports_to_send(self, practice: Practice) -> models.QuerySet[LabOrder]:
        """`practice`'s analysed lab orders it has not acknowledged yet (features/messaging.feature)."""
        return (
            self.filter(
                sample__practice=practice,
                analysed_at__isnull=False,
                report_acknowledged_at__isnull=True,
            )
            .select_related("sample")
            .order_by("pk")
        )

    @transaction.atomic
    def receive(self, *, practice: Practice, details: LabOrderDetails) -> LabOrder:
        """Record a lab order (DF23) from `practice` once, however often it arrives
        (features/messaging.feature)."""
        sample, _ = Sample.objects.get_or_create(
            practice=practice, sample_id=details.sample_id
        )
        lab_order, _ = self.get_or_create(
            sample=sample,
            test=details.test,
            defaults={
                "screened_indication": details.screened_indication,
                "registered_sex": details.registered_sex,
                "age": details.age,
                "ordered_at": details.ordered_at,
            },
        )
        return lab_order

    @transaction.atomic
    def acknowledge(
        self, *, practice: Practice, report_ids: list[int], now: datetime
    ) -> None:
        """`practice` has these lab reports of its own: hand them out no more."""
        self.filter(
            sample__practice=practice,
            pk__in=report_ids,
            report_acknowledged_at__isnull=True,
        ).update(report_acknowledged_at=now)


class LabOrder(models.Model):
    """One test on a sample, as the lab order (DF23) said: no patient field (features/access.feature)."""

    sample = models.ForeignKey(
        Sample, on_delete=models.PROTECT, related_name="lab_orders"
    )
    test = models.CharField(max_length=8, choices=Test.choices)
    # Whether the general practitioner's indication is a screened one (features/screening.feature, features/messaging.feature);
    # the laboratory never learns which indication.
    screened_indication = models.BooleanField(default=False)
    registered_sex = models.CharField(max_length=6, choices=RegisteredSex.choices)
    age = models.PositiveSmallIntegerField()
    # No general practitioner: the sample's practice says who ordered (features/access.feature).
    ordered_at = models.DateTimeField()
    # Absent until the analyser has run.
    analysed_at = models.DateTimeField(null=True, blank=True)
    results = models.JSONField(null=True, blank=True)
    # Absent for ferritin, which is never screened (features/lab.feature), and until analysed.
    screening_result = models.CharField(
        max_length=22, choices=ScreeningResult.choices, null=True, blank=True
    )
    # Present only when not screened (features/screening.feature); no score is ever stored (features/screening.feature).
    not_screened_reason = models.CharField(
        max_length=22, choices=NotScreened.choices, null=True, blank=True
    )
    # The screening model that screened this CBC (features/screening.feature); absent when not screened.
    screened_by = models.ForeignKey(
        ScreeningModel,
        on_delete=models.PROTECT,
        related_name="screening_results",
        null=True,
        blank=True,
    )
    # Absent until the general practitioner's app confirmed it has the lab report.
    report_acknowledged_at = models.DateTimeField(null=True, blank=True)

    objects = LabOrderManager()

    class Meta:
        constraints = (
            models.UniqueConstraint(
                fields=["sample", "test"], name="one_test_per_sample"
            ),
        )

    def __str__(self) -> str:
        return f"{self.sample.sample_id} {self.test}"

    def not_eligible(self) -> NotScreened | None:
        """NOT_ELIGIBLE if the screening excludes the CBC: an indication not screened, a
        registered sex other than female, or an age outside the trained range.
        Which of them is never recorded: nobody acts on it (features/screening.feature)."""
        eligible = (
            self.screened_indication
            and self.registered_sex == RegisteredSex.of_nhanes(ELIGIBLE_SEX)
            and ELIGIBLE_AGES[0] <= self.age <= ELIGIBLE_AGES[1]
        )
        return None if eligible else NotScreened.NOT_ELIGIBLE

    @property
    def ferritin_suggested(self) -> bool:
        """All the lab report says of screening (features/reports.feature, features/messaging.feature)."""
        return self.screening_result == ScreeningResult.FERRITIN_SUGGESTED

    @transaction.atomic
    def run_analyser(self, *, directory: Path | None, now: datetime) -> LabOrder:
        """Record what the analyser measures on the stored sample for the test (features/lab.feature), screen a CBC with the deployed model in `directory`, and so release its
        lab report at once (features/screening.feature): the report goes out with the analysis, never before."""
        # Read again under the write lock: this copy may predate another analysis.
        self.refresh_from_db(fields=["analysed_at"])
        if self.analysed_at is not None:
            raise ValidationError(
                "This test has already been analysed.", code="already_analysed"
            )
        # The sample's contents: the NHANES participant whose number starts the
        # sample ID, so every sample of one patient measures the same.
        seqn = self.sample.sample_id.split("-")[0]
        tube = (
            Participant.objects.filter(seqn=int(seqn)).first()
            if seqn.isdigit()
            else None
        )
        if tube is None:
            raise ValidationError(
                "The analyser has no tube for this sample ID.", code="no_tube"
            )
        self.results = tube.measure(Test(self.test))
        self.analysed_at = now
        if self.test == Test.CBC:
            self._screen(directory)
        self.save(
            update_fields=[
                "results",
                "analysed_at",
                "screening_result",
                "not_screened_reason",
                "screened_by",
            ]
        )
        return self

    def _screen(self, directory: Path | None) -> None:
        """Set an analysed CBC's screening result: the model's decision, or not
        screened with the first reason (features/screening.feature). Nothing else of it is kept (features/screening.feature)."""
        reason = self.not_eligible()
        if reason is None:
            deployed = Deployment.objects.screener(directory)
            if isinstance(deployed, NoUsableModel):
                reason = NotScreened.because(deployed)
            else:
                suggested = deployed.suggests_ferritin(self.results or {}, self.age)
                self.screening_result = (
                    ScreeningResult.FERRITIN_SUGGESTED
                    if suggested
                    else ScreeningResult.FERRITIN_NOT_SUGGESTED
                )
                self.screened_by = deployed.screening_model
                return
        self.screening_result = ScreeningResult.NOT_SCREENED
        self.not_screened_reason = reason
