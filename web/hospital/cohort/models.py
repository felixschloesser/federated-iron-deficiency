"""The laboratory's lab records (DS1) and the training cohort its laboratory
director provides from them (features/hospital/training_cohort.feature)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Count, Q

from ml.cohort import CBC_VARS, ELIGIBLE_AGES, ELIGIBLE_SEX, FEATURES, FERRITIN_CUTOFF
from ml.training_cohort import remove_training_cohort, sha256, write_training_cohort
from web.shared.accounts.models import User
from web.shared.vocabulary import RegisteredSex

# Below these the startup's code cannot train or validate on the cohort, and
# each past patient weighs more in what the model learns.
MIN_PAST_PATIENTS = 100
MIN_PER_CLASS = 10


@dataclass(frozen=True)
class Summary:
    """What a training cohort would hold: counts, never records."""

    past_patients: int
    iron_deficient: int


class LabRecordQuerySet(models.QuerySet["LabRecord"]):
    def eligible(self) -> LabRecordQuerySet:
        """Past patients the training cohort holds: eligible, with a complete CBC
        and a ferritin result; in the order the laboratory recorded them."""
        return self.filter(
            registered_sex=RegisteredSex.of_nhanes(ELIGIBLE_SEX),
            age__range=ELIGIBLE_AGES,
            ferritin__isnull=False,
            cbc__has_keys=CBC_VARS,
        ).order_by("pk")

    def summary(self) -> Summary:
        counts = self.eligible().aggregate(
            past_patients=Count("pk"),
            iron_deficient=Count("pk", filter=Q(ferritin__lt=FERRITIN_CUTOFF)),
        )
        return Summary(counts["past_patients"], counts["iron_deficient"])

    def training_cohort(self) -> pd.DataFrame:
        """The eligible past patients as the startup's code trains on them: the 13
        CBC values, age and whether ferritin was below the cutoff; nothing else."""
        rows = [
            [*(record.cbc[var] for var in CBC_VARS), float(record.age)]
            + [int(record.ferritin is not None and record.ferritin < FERRITIN_CUTOFF)]
            for record in self.eligible().only("cbc", "age", "ferritin")
        ]
        return pd.DataFrame(rows, columns=[*FEATURES, "iron_deficient"]).astype(
            dict.fromkeys(FEATURES, "float64")
        )


class LabRecord(models.Model):
    """A past patient's CBC and ferritin result, as the laboratory holds them."""

    registered_sex = models.CharField(max_length=6, choices=RegisteredSex.choices)
    age = models.PositiveSmallIntegerField()
    # The CBC values keyed by NHANES variable name (ml.cohort.CBC_VARS); one
    # the analyser did not report is absent.
    cbc = models.JSONField()
    # Absent when no ferritin was measured.
    ferritin = models.FloatField(null=True, blank=True)

    objects = LabRecordQuerySet.as_manager()


class TrainingCohortManager(models.Manager["TrainingCohort"]):
    def provided(self) -> TrainingCohort | None:
        """The training cohort the startup's code may read, if one is provided."""
        return self.filter(withdrawn_at__isnull=True).first()

    @transaction.atomic
    def provide(self, *, directory: Path, by: User, now: datetime) -> TrainingCohort:
        """Extract the training cohort from the lab records and make it the one
        the startup's code at this hospital reads, in place of any provided
        before."""
        rows = LabRecord.objects.training_cohort()
        iron_deficient = int(rows["iron_deficient"].sum())
        refusals = [
            refusal
            for refusal in (
                _too_few(
                    len(rows),
                    MIN_PAST_PATIENTS,
                    "eligible past patients",
                    "too_few_past_patients",
                ),
                _too_few(
                    iron_deficient,
                    MIN_PER_CLASS,
                    "iron-deficient past patients",
                    "too_few_iron_deficient",
                ),
                _too_few(
                    len(rows) - iron_deficient,
                    MIN_PER_CLASS,
                    "past patients who are not iron deficient",
                    "too_few_not_iron_deficient",
                ),
            )
            if refusal is not None
        ]
        if refusals:
            raise ValidationError(refusals)
        digest = sha256(rows)
        earlier = self.provided()
        if earlier is not None and earlier.sha256 == digest:
            raise ValidationError(
                "The lab records have not changed since this training cohort was"
                " provided.",
                code="unchanged",
            )
        if earlier is not None:
            earlier.withdraw(by=by, now=now)
        cohort = self.create(
            sha256=digest,
            past_patients=len(rows),
            iron_deficient=iron_deficient,
            provided_at=now,
            provided_by=by,
        )
        # Last: should writing fail, nothing above is recorded.
        write_training_cohort(rows, directory)
        return cohort

    @transaction.atomic
    def withdraw(self, *, directory: Path, by: User, now: datetime) -> TrainingCohort:
        """Withdraw the provided training cohort: the startup's code at this
        hospital finds none from its next round."""
        provided = self.provided()
        if provided is None:
            raise ValidationError(
                "No training cohort is provided.", code="nothing_provided"
            )
        provided.withdraw(by=by, now=now)
        remove_training_cohort(directory)
        return provided


def _too_few(count: int, minimum: int, what: str, code: str) -> ValidationError | None:
    if count >= minimum:
        return None
    return ValidationError(
        f"A training cohort needs at least {minimum} {what}; the lab records hold"
        f" {count}.",
        code=code,
    )


class TrainingCohort(models.Model):
    """One training cohort the laboratory director provided: what it held and
    its SHA-256, never its rows; withdrawn when the director withdrew it or
    provided another."""

    sha256 = models.CharField(max_length=64)
    past_patients = models.PositiveIntegerField()
    iron_deficient = models.PositiveIntegerField()
    provided_at = models.DateTimeField()
    provided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    # Absent while the startup's code may read it.
    withdrawn_at = models.DateTimeField(null=True, blank=True)
    withdrawn_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )

    objects = TrainingCohortManager()

    class Meta:
        ordering = ("-provided_at", "-pk")
        constraints = (
            models.UniqueConstraint(
                models.Value(1),
                condition=Q(withdrawn_at__isnull=True),
                name="one_provided_training_cohort",
                violation_error_code="one_provided_training_cohort",
                violation_error_message="One training cohort is provided at a time.",
            ),
            models.CheckConstraint(
                condition=Q(withdrawn_at__isnull=True, withdrawn_by__isnull=True)
                | Q(withdrawn_at__isnull=False, withdrawn_by__isnull=False),
                name="withdrawn_by_someone",
                violation_error_code="withdrawn_by_someone",
                violation_error_message="A withdrawal records who and when.",
            ),
        )

    def __str__(self) -> str:
        return self.sha256

    @transaction.atomic
    def withdraw(self, *, by: User, now: datetime) -> None:
        self.withdrawn_at = now
        self.withdrawn_by = by
        self.save(update_fields=["withdrawn_at", "withdrawn_by"])
