"""The laboratory's lab records and the training cohort the laboratory director
provides from them (features/hospital/training_cohort.feature)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Count, Q

from ml.cohort import (
    CBC_VARS,
    ELIGIBLE_AGES,
    FEATURES,
    FERRITIN_CUTOFF,
    INFLAMED_FERRITIN_CUTOFF,
    INFLAMMATION_CRP,
    iron_deficient,
)
from ml.training_cohort import remove_training_cohort, sha256, write_training_cohort
from web.hospital.lab.models import SCREENED_INDICATIONS
from web.shared.accounts.models import User
from web.shared.vocabulary import ClinicalIndication, RegisteredSex

# Below these counts the startup's code cannot train and validate on the cohort,
# and each past patient would weigh too much in what the model learns.
MIN_PAST_PATIENTS = 100
MIN_PER_CLASS = 10


@dataclass(frozen=True)
class Summary:
    """What a training cohort would hold, as counts only, never records."""

    past_patients: int
    iron_deficient: int
    # Past patients who are eligible except for the CRP result the label needs;
    # they are left out.
    without_crp: int


class LabRecordQuerySet(models.QuerySet["LabRecord"]):
    def eligible(self) -> LabRecordQuerySet:
        """The past patients a training cohort holds, in the order the laboratory
        recorded them: eligible, with a complete CBC ordered for a screened
        indication, a ferritin and a CRP result. None is at the start of
        pregnancy, because the model learns only from CBCs like those it screens."""
        return self._eligible_but_for_crp().filter(crp__isnull=False)

    def _eligible_but_for_crp(self) -> LabRecordQuerySet:
        return self.filter(
            registered_sex=RegisteredSex.FEMALE,
            age__range=ELIGIBLE_AGES,
            clinical_indication__in=SCREENED_INDICATIONS,
            ferritin__isnull=False,
            cbc__has_keys=CBC_VARS,
        ).order_by("pk")

    def summary(self) -> Summary:
        with_crp = Q(crp__isnull=False)
        # The rule of ml.cohort.iron_deficient, written so the database can count it.
        deficient = Q(ferritin__lt=FERRITIN_CUTOFF) | Q(
            crp__gt=INFLAMMATION_CRP, ferritin__lt=INFLAMED_FERRITIN_CUTOFF
        )
        counts = self._eligible_but_for_crp().aggregate(
            past_patients=Count("pk", filter=with_crp),
            iron_deficient=Count("pk", filter=with_crp & deficient),
            without_crp=Count("pk", filter=~with_crp),
        )
        return Summary(
            counts["past_patients"], counts["iron_deficient"], counts["without_crp"]
        )

    def training_cohort(self) -> pd.DataFrame:
        """The eligible past patients in the form the startup's code trains on:
        the 13 CBC values, age, and whether iron deficient, nothing else.
        Ferritin and CRP are used only to compute the label and never leave."""
        records = self.eligible().only("cbc", "age", "ferritin", "crp")
        rows = pd.DataFrame(
            [
                [*(record.cbc[var] for var in CBC_VARS), float(record.age)]
                for record in records
            ],
            columns=FEATURES,
            dtype="float64",
        )
        label = iron_deficient(
            pd.Series([record.ferritin for record in records], dtype="float64"),
            pd.Series([record.crp for record in records], dtype="float64"),
        )
        return rows.assign(iron_deficient=label.astype(int).to_numpy())


class LabRecord(models.Model):
    """A past patient's CBC and ferritin result, as the laboratory holds them."""

    registered_sex = models.CharField(max_length=6, choices=RegisteredSex.choices)
    age = models.PositiveSmallIntegerField()
    # The CBC values keyed by NHANES variable name (ml.cohort.CBC_VARS); a value
    # the analyser did not report is missing.
    cbc = models.JSONField()
    # None when no ferritin was measured.
    ferritin = models.FloatField(null=True, blank=True)
    # C-reactive protein, mg/L; None when none was measured.
    crp = models.FloatField(null=True, blank=True)
    # Why the CBC was ordered; None on a record from before orders gave a reason.
    clinical_indication = models.CharField(
        max_length=19, choices=ClinicalIndication.choices, null=True, blank=True
    )

    objects = LabRecordQuerySet.as_manager()


class TrainingCohortManager(models.Manager["TrainingCohort"]):
    def provided(self) -> TrainingCohort | None:
        """The training cohort the startup's code may read, if one is provided."""
        return self.filter(withdrawn_at__isnull=True).first()

    @transaction.atomic
    def provide(self, *, directory: Path, by: User, now: datetime) -> TrainingCohort:
        """Extract the training cohort from the lab records and make it the one
        the startup's code at this hospital reads, replacing any provided before."""
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
        # Written last, so that if writing fails the transaction rolls back and
        # nothing above is recorded.
        write_training_cohort(rows, directory)
        return cohort

    @transaction.atomic
    def withdraw(self, *, directory: Path, by: User, now: datetime) -> TrainingCohort:
        """Withdraw the provided training cohort; from its next round, the
        startup's code at this hospital finds none."""
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
    """A training cohort the laboratory director provided. It records the counts
    and the SHA-256, never the rows. It is withdrawn when the director withdraws
    it or provides another."""

    sha256 = models.CharField(max_length=64)
    past_patients = models.PositiveIntegerField()
    iron_deficient = models.PositiveIntegerField()
    provided_at = models.DateTimeField()
    provided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    # None while the startup's code may read it.
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
