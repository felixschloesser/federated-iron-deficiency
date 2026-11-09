"""The hospital's samples and the practices it works with
(features/hospital/lab.feature)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TypedDict

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Exists, OuterRef
from django.utils.text import slugify
from django_stubs_ext import WithAnnotations

from ml.cohort import ELIGIBLE_AGES
from web.hospital.analyser import port as analyser
from web.hospital.deployment.models import (
    DeployedScreeningModel,
    Deployment,
    NoUsableModel,
)
from web.shared.parsing import once_each, parsed
from web.shared.vocabulary import ClinicalIndication, RegisteredSex, Test

# The indications whose CBC the hospital screens: for these the guidelines order
# a CBC without ferritin first, so a ferritin suggestion can add something.
SCREENED_INDICATIONS = (
    ClinicalIndication.SUSPECTED_ANAEMIA,
    ClinicalIndication.SUSPECTED_IBS,
    ClinicalIndication.UNEXPLAINED_FATIGUE,
)


class ScreeningResult(models.TextChoices):
    """What screening records of a CBC: the model's decision; not screened, for a
    CBC the screening does not cover (without saying why); or screening failed,
    when no deployed screening model was usable."""

    FERRITIN_SUGGESTED = "ferritin_suggested", "Ferritin suggested"
    FERRITIN_NOT_SUGGESTED = "ferritin_not_suggested", "Ferritin not suggested"
    NOT_SCREENED = "not_screened", "Not screened"
    SCREENING_FAILED = "screening_failed", "Screening failed"


class PracticeManager(models.Manager["Practice"]):
    @transaction.atomic
    def add(self, *, name: str) -> Practice:
        """Register a practice by its name, once; a name whose slug another
        practice already has is refused."""
        practice = self.filter(name=name).first()
        if practice is None:
            practice = Practice(name=name, slug=slugify(name))
            practice.full_clean()
            practice.save()
        return practice


class Practice(models.Model):
    """A practice the hospital works with. Its name never changes, and its app
    calls as the name's slug."""

    name = models.CharField(max_length=100, unique=True)
    # The name the practice's app calls as; derived from the name.
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
    """A sample, identified by the sample ID on its label together with the
    practice that sent it, because two practices may use the same sample ID. It
    arrives with its lab order; a later test on it is measured on the stored
    sample."""

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
    """What a lab order says, as it arrived: no patient name, no values. It
    becomes a test request only through TestRequest.objects.receive, which checks
    each part against the model fields."""

    sample_id: str
    test: str | None
    # None for ferritin, which needs no clinical indication.
    clinical_indication: str | None
    registered_sex: str | None
    age: int | None
    collected_at: datetime | None


class StoredSample(TypedDict):
    stored_sample: bool


class TestRequestManager(models.Manager["TestRequest"]):
    """Test requests as laboratory staff see and handle them; they hold no patient
    field."""

    def to_analyse(self) -> models.QuerySet[WithAnnotations[TestRequest, StoredSample]]:
        """Test requests the analyser has not run yet, oldest sample first. A sample
        arrives with its lab order; it is a stored sample once another test on it
        has been analysed."""
        analysed_on_same_sample = TestRequest.objects.filter(
            sample=OuterRef("sample"), analysed_at__isnull=False
        )
        return (
            self.filter(analysed_at__isnull=True)
            .annotate(stored_sample=Exists(analysed_on_same_sample))
            .select_related("sample")
            .order_by("collected_at", "pk")
        )

    def analysed(self) -> models.QuerySet[TestRequest]:
        """Analysed test requests, newest first."""
        return (
            self.filter(analysed_at__isnull=False)
            .select_related("sample")
            .order_by("-analysed_at", "-pk")
        )

    def reports_to_send(self, practice: Practice) -> models.QuerySet[TestRequest]:
        """`practice`'s analysed test requests whose lab reports it has not
        acknowledged yet."""
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
        """Receive a lab order from `practice` as a test request, recorded once
        however often it arrives. Raises ValidationError with one error for each
        part the Sample or TestRequest fields refuse (web/shared/parsing.py)."""
        values = parsed(
            (Sample, {"sample_id": details.sample_id}),
            (
                TestRequest,
                {
                    "test": details.test,
                    "clinical_indication": details.clinical_indication,
                    "registered_sex": details.registered_sex,
                    "age": details.age,
                    "collected_at": details.collected_at,
                },
            ),
        )
        sample, _ = Sample.objects.get_or_create(
            practice=practice, sample_id=values.pop("sample_id")
        )
        test_request, _ = self.get_or_create(
            sample=sample, test=values.pop("test"), defaults=values
        )
        return test_request

    @transaction.atomic
    def acknowledge(
        self,
        *,
        practice: Practice,
        lab_reports: list[tuple[str, str | None]],
        now: datetime,
    ) -> None:
        """Record that `practice` has these lab reports of its own, each named by
        sample ID and test, so they are handed out no more. Naming one twice
        refuses them all."""
        once_each("acknowledgements", lab_reports, code="duplicate_lab_report")
        named = models.Q(pk__in=[])
        for sample_id, test in lab_reports:
            named |= models.Q(sample__sample_id=sample_id, test=test)
        self.filter(
            named, sample__practice=practice, report_acknowledged_at__isnull=True
        ).update(report_acknowledged_at=now)


class TestRequest(models.Model):
    """One test on a sample, as its lab order asked for it; it holds no patient
    field."""

    sample = models.ForeignKey(
        Sample, on_delete=models.PROTECT, related_name="test_requests"
    )
    test = models.CharField(max_length=8, choices=Test.choices)
    # Why the general practitioner ordered it; None for ferritin.
    clinical_indication = models.CharField(
        max_length=19, choices=ClinicalIndication.choices, null=True, blank=True
    )
    registered_sex = models.CharField(max_length=6, choices=RegisteredSex.choices)
    age = models.PositiveSmallIntegerField()
    # No general practitioner field: the sample's practice says who ordered.
    # When the practice collected the sample: how old it is.
    collected_at = models.DateTimeField()
    # None until the analyser has run.
    analysed_at = models.DateTimeField(null=True, blank=True)
    results = models.JSONField(null=True, blank=True)
    # None for ferritin, which is never screened, and until analysed.
    screening_result = models.CharField(
        max_length=22, choices=ScreeningResult.choices, null=True, blank=True
    )
    # The deployed screening model that screened this CBC; None when not screened.
    screened_by = models.ForeignKey(
        DeployedScreeningModel,
        on_delete=models.PROTECT,
        related_name="screening_results",
        null=True,
        blank=True,
    )
    # None until the practice's app confirms it has the lab report.
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

    def is_eligible(self) -> bool:
        """Whether the screening covers the CBC: a screened indication, registered
        sex female, and an age in the trained range. Which condition excluded a
        CBC is not recorded, because nobody acts on it."""
        return (
            self.clinical_indication in SCREENED_INDICATIONS
            and self.registered_sex == RegisteredSex.FEMALE
            and ELIGIBLE_AGES[0] <= self.age <= ELIGIBLE_AGES[1]
        )

    @property
    def ferritin_suggested(self) -> bool:
        """Whether ferritin is suggested: all the lab report says about screening."""
        return self.screening_result == ScreeningResult.FERRITIN_SUGGESTED

    @transaction.atomic
    def run_analyser(self, *, directory: Path, now: datetime) -> TestRequest:
        """Record what the analyser measures for this test, screen a CBC with the
        deployed screening model in `directory`, and so release the lab report:
        it goes out with the analysis, never before."""
        # Read analysed_at again inside the transaction: this in-memory copy may
        # predate another analysis of the same test.
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
                "screened_by",
            ]
        )
        return self

    def _screen(self, directory: Path) -> None:
        """Set an analysed CBC's screening result: not screened when the screening
        does not cover it, screening failed without a usable deployed screening
        model, otherwise the model's decision. Nothing else about the screening is
        kept."""
        if not self.is_eligible():
            self.screening_result = ScreeningResult.NOT_SCREENED
            return
        deployed = Deployment.objects.screener(directory)
        if isinstance(deployed, NoUsableModel):
            self.screening_result = ScreeningResult.SCREENING_FAILED
            return
        suggested = deployed.suggests_ferritin(self.results or {}, self.age)
        self.screening_result = (
            ScreeningResult.FERRITIN_SUGGESTED
            if suggested
            else ScreeningResult.FERRITIN_NOT_SUGGESTED
        )
        self.screened_by = deployed.deployed_screening_model
