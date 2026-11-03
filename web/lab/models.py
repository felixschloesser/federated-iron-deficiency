"""Laboratory staff and samples (terms: docs/spec/requirements.md §1)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TypedDict, assert_never

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Exists, OuterRef
from django_stubs_ext import WithAnnotations

from iron_deficiency.dataset import ELIGIBLE_AGES, ELIGIBLE_SEX
from web.deployment.models import Deployment, NoUsableModel, ScreeningModel
from web.nhanes.models import Participant
from web.vocabulary import ClinicalIndication, RegisteredSex, Test


class ScreeningResult(models.TextChoices):
    FERRITIN_SUGGESTED = "ferritin_suggested", "Ferritin suggested"
    FERRITIN_NOT_SUGGESTED = "ferritin_not_suggested", "Ferritin not suggested"
    NOT_SCREENED = "not_screened", "Not screened"


class NotScreened(models.TextChoices):
    """Why a CBC was not screened: the first failing condition (R5), else why
    there is no usable deployed model (web.deployment.models.NoUsableModel)."""

    INDICATION = "indication", "clinical indication not screened"
    SEX = "sex", "registered sex not female"
    AGE = "age", f"age outside {ELIGIBLE_AGES[0]}–{ELIGIBLE_AGES[1]}"
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
            case NotScreened.INDICATION | NotScreened.SEX | NotScreened.AGE:
                return False
            case NotScreened.NO_DEPLOYED_MODEL | NotScreened.DEPLOYED_MODEL_CHANGED:
                return True
            case _:
                assert_never(self)


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


@dataclass(frozen=True)
class LabOrderDetails:
    """What a lab order (DF23) says: no patient name, no values (R25)."""

    sample_id: str
    test: Test
    indication: ClinicalIndication | None
    registered_sex: RegisteredSex
    age: int
    general_practitioner: str
    ordered_at: datetime


class StoredSample(TypedDict):
    stored_sample: bool


class LabOrderManager(models.Manager["LabOrder"]):
    """What laboratory staff see: lab orders, which hold no patient field (R14)."""

    def to_analyse(self) -> models.QuerySet[WithAnnotations[LabOrder, StoredSample]]:
        """Tests the analyser has not run yet. A sample arrives with its lab order; it
        is a stored sample once another test on it has been analysed (R2)."""
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

    def reports_to_send(self, client: str) -> models.QuerySet[LabOrder]:
        """`client`'s analysed lab orders it has not acknowledged yet (R23, R24)."""
        return (
            self.filter(
                sample__client=client,
                analysed_at__isnull=False,
                report_acknowledged_at__isnull=True,
            )
            .select_related("sample")
            .order_by("pk")
        )

    @transaction.atomic
    def record(self, *, client: str, details: LabOrderDetails) -> LabOrder:
        """Record a lab order (DF23) from `client` once, however often it arrives
        (R22, O18)."""
        sample, _ = Sample.objects.get_or_create(
            client=client, sample_id=details.sample_id
        )
        lab_order, _ = self.get_or_create(
            sample=sample,
            test=details.test,
            defaults={
                "indication": details.indication,
                "registered_sex": details.registered_sex,
                "age": details.age,
                "general_practitioner": details.general_practitioner,
                "ordered_at": details.ordered_at,
            },
        )
        return lab_order

    @transaction.atomic
    def acknowledge(self, *, client: str, report_ids: list[int], now: datetime) -> None:
        """`client` has these lab reports of its own: hand them out no more."""
        self.filter(
            sample__client=client,
            pk__in=report_ids,
            report_acknowledged_at__isnull=True,
        ).update(report_acknowledged_at=now)


class LabOrder(models.Model):
    """One test on a sample, as the lab order (DF23) said: no patient field (R14)."""

    sample = models.ForeignKey(
        Sample, on_delete=models.PROTECT, related_name="lab_orders"
    )
    test = models.CharField(max_length=8, choices=Test.choices)
    indication = models.CharField(
        max_length=24, choices=ClinicalIndication.choices, null=True, blank=True
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
    # The screening model that screened this CBC (R6); absent when not screened.
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
        """The first condition R4 fails, in the order indication, sex, age."""
        if (
            self.indication is None
            or not ClinicalIndication(self.indication).is_screened()
        ):
            return NotScreened.INDICATION
        if self.registered_sex != RegisteredSex.of_nhanes(ELIGIBLE_SEX):
            return NotScreened.SEX
        if not ELIGIBLE_AGES[0] <= self.age <= ELIGIBLE_AGES[1]:
            return NotScreened.AGE
        return None

    @property
    def ferritin_suggested(self) -> bool:
        """All the lab report says of screening (R9, R25)."""
        return self.screening_result == ScreeningResult.FERRITIN_SUGGESTED

    @transaction.atomic
    def run_analyser(self, *, directory: Path | None, now: datetime) -> LabOrder:
        """Record what the analyser measures on the stored sample for the test (R3,
        R12), screen a CBC with the deployed model in `directory`, and so release its
        lab report at once (R8): the report goes out with the analysis, never before."""
        # Read again under the write lock: this copy may predate another analysis.
        self.refresh_from_db(fields=["analysed_at"])
        if self.analysed_at is not None:
            raise ValidationError(
                "This test has already been analysed.", code="already_analysed"
            )
        # The sample's contents: the NHANES participant whose number starts the
        # sample ID, so every sample of one patient measures the same (spec §8).
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
        screened with the first reason (R4, R5, R19). Nothing else of it is kept (R7)."""
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
