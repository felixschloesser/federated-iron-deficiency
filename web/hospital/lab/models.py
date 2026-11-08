"""The hospital's samples and the practices it works with (terms: glossary.toml)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TypedDict, assert_never

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Exists, OuterRef
from django.utils.text import slugify
from django_stubs_ext import WithAnnotations

from ml.cohort import ELIGIBLE_AGES, ELIGIBLE_SEX
from web.hospital.analyser import port as analyser
from web.hospital.deployment.models import (
    DeployedScreeningModel,
    Deployment,
    NotScreened,
)
from web.shared.vocabulary import ClinicalIndication, RegisteredSex, Test


def is_screened_indication(indication: ClinicalIndication) -> bool:
    """Whether the hospital screens a CBC ordered for this indication: the
    guidelines order a CBC without ferritin first, so a suggestion can add something."""
    match indication:
        case (
            ClinicalIndication.SUSPECTED_ANAEMIA
            | ClinicalIndication.SUSPECTED_IBS
            | ClinicalIndication.UNEXPLAINED_FATIGUE
        ):
            return True
        case (
            ClinicalIndication.START_OF_PREGNANCY
            | ClinicalIndication.CKD_FOLLOW_UP
            | ClinicalIndication.OTHER
        ):
            return False
        case _:
            assert_never(indication)


def screened_indications() -> list[ClinicalIndication]:
    """Every indication whose CBC the hospital screens."""
    return [
        indication
        for indication in ClinicalIndication
        if is_screened_indication(indication)
    ]


class ScreeningResult(models.TextChoices):
    FERRITIN_SUGGESTED = "ferritin_suggested", "Ferritin suggested"
    FERRITIN_NOT_SUGGESTED = "ferritin_not_suggested", "Ferritin not suggested"
    NOT_SCREENED = "not_screened", "Not screened"


class PracticeManager(models.Manager["Practice"]):
    @transaction.atomic
    def add(self, *, name: str) -> Practice:
        """Register a practice the hospital works with by its name, once; a name
        whose slug another practice has is refused."""
        practice = self.filter(name=name).first()
        if practice is None:
            practice = Practice(name=name, slug=slugify(name))
            practice.full_clean()
            practice.save()
        return practice


class Practice(models.Model):
    """A practice the hospital works with, by its name (glossary.toml), which
    never changes; its app calls as the name's slug."""

    name = models.CharField(max_length=100, unique=True)
    # What the practice's app calls as; follows from the name.
    slug = models.SlugField(max_length=100, editable=False)

    objects = PracticeManager()

    class Meta:
        constraints = (
            models.UniqueConstraint(
                fields=["slug"],
                name="one_practice_per_slug",
                violation_error_code="slug_taken",
                violation_error_message="Another practice's name has this slug.",
            ),
        )

    def __str__(self) -> str:
        return self.name


class Sample(models.Model):
    """A sample, known by the sample ID on its label and the practice that sent it
    (features/hospital/lab.feature): two practices may use the same sample ID. It arrives with its lab
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
    """What a lab order (DF23) says: no patient name, no values (features/hospital/lab.feature)."""

    sample_id: str
    test: Test
    # Absent for ferritin, which takes none.
    clinical_indication: ClinicalIndication | None
    registered_sex: RegisteredSex
    age: int
    ordered_at: datetime


class StoredSample(TypedDict):
    stored_sample: bool


class TestRequestManager(models.Manager["TestRequest"]):
    """What laboratory staff see: test requests, which hold no patient field (features/practice/access.feature)."""

    def to_analyse(self) -> models.QuerySet[WithAnnotations[TestRequest, StoredSample]]:
        """Tests the analyser has not run yet. A sample arrives with its lab order; it
        is a stored sample once another test on it has been analysed."""
        analysed_on_same_sample = TestRequest.objects.filter(
            sample=OuterRef("sample"), analysed_at__isnull=False
        )
        return (
            self.filter(analysed_at__isnull=True)
            .annotate(stored_sample=Exists(analysed_on_same_sample))
            .select_related("sample")
            .order_by("ordered_at", "pk")
        )

    def analysed(self) -> models.QuerySet[TestRequest]:
        """Tests with results, newest first."""
        return (
            self.filter(analysed_at__isnull=False)
            .select_related("sample")
            .order_by("-analysed_at", "-pk")
        )

    def reports_to_send(self, practice: Practice) -> models.QuerySet[TestRequest]:
        """`practice`'s analysed test requests it has not acknowledged yet."""
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
    def receive(self, *, practice: Practice, details: LabOrderDetails) -> TestRequest:
        """Receive a lab order (DF23) from `practice` as a test request, once,
        however often it arrives."""
        sample, _ = Sample.objects.get_or_create(
            practice=practice, sample_id=details.sample_id
        )
        test_request, _ = self.get_or_create(
            sample=sample,
            test=details.test,
            defaults={
                "clinical_indication": details.clinical_indication,
                "registered_sex": details.registered_sex,
                "age": details.age,
                "ordered_at": details.ordered_at,
            },
        )
        return test_request

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


class TestRequest(models.Model):
    """A test request: one test on a sample, as its lab order (DF23) said; no patient field (features/practice/access.feature)."""

    sample = models.ForeignKey(
        Sample, on_delete=models.PROTECT, related_name="test_requests"
    )
    test = models.CharField(max_length=8, choices=Test.choices)
    # Why the general practitioner ordered it; absent for ferritin.
    clinical_indication = models.CharField(
        max_length=19, choices=ClinicalIndication.choices, null=True, blank=True
    )
    registered_sex = models.CharField(max_length=6, choices=RegisteredSex.choices)
    age = models.PositiveSmallIntegerField()
    # No general practitioner: the sample's practice says who ordered.
    ordered_at = models.DateTimeField()
    # Absent until the analyser has run.
    analysed_at = models.DateTimeField(null=True, blank=True)
    results = models.JSONField(null=True, blank=True)
    # Absent for ferritin, which is never screened, and until analysed.
    screening_result = models.CharField(
        max_length=22, choices=ScreeningResult.choices, null=True, blank=True
    )
    # Present only when not screened; no score is ever stored.
    not_screened_reason = models.CharField(
        max_length=22, choices=NotScreened.choices, null=True, blank=True
    )
    # The screening model that screened this CBC; absent when not screened.
    screened_by = models.ForeignKey(
        DeployedScreeningModel,
        on_delete=models.PROTECT,
        related_name="screening_results",
        null=True,
        blank=True,
    )
    # Absent until the general practitioner's app confirmed it has the lab report.
    report_acknowledged_at = models.DateTimeField(null=True, blank=True)

    objects = TestRequestManager()

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
        Which of them is never recorded: nobody acts on it."""
        eligible = (
            self.clinical_indication is not None
            and is_screened_indication(ClinicalIndication(self.clinical_indication))
            and self.registered_sex == RegisteredSex.of_nhanes(ELIGIBLE_SEX)
            and ELIGIBLE_AGES[0] <= self.age <= ELIGIBLE_AGES[1]
        )
        return None if eligible else NotScreened.NOT_ELIGIBLE

    @property
    def ferritin_suggested(self) -> bool:
        """All the lab report says of screening."""
        return self.screening_result == ScreeningResult.FERRITIN_SUGGESTED

    @transaction.atomic
    def run_analyser(self, *, directory: Path | None, now: datetime) -> TestRequest:
        """Record what the analyser measures on the stored sample for the test, screen a CBC with the deployed screening model in `directory`, and so release its
        lab report at once: the report goes out with the analysis, never before."""
        # Read again under the write lock: this copy may predate another analysis.
        self.refresh_from_db(fields=["analysed_at"])
        if self.analysed_at is not None:
            raise ValidationError(
                "This test has already been analysed.", code="already_analysed"
            )
        results = analyser.measure(self.sample.sample_id, Test(self.test))
        if results is None:
            raise ValidationError(
                "The analyser has no tube for this sample ID.", code="no_tube"
            )
        self.results = results
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
        screened with the first reason. Nothing else of it is kept."""
        reason = self.not_eligible()
        if reason is None:
            deployed = Deployment.objects.screener(directory)
            if isinstance(deployed, NotScreened):
                reason = deployed
            else:
                suggested = deployed.suggests_ferritin(self.results or {}, self.age)
                self.screening_result = (
                    ScreeningResult.FERRITIN_SUGGESTED
                    if suggested
                    else ScreeningResult.FERRITIN_NOT_SUGGESTED
                )
                self.screened_by = deployed.deployed_screening_model
                return
        self.screening_result = ScreeningResult.NOT_SCREENED
        self.not_screened_reason = reason
