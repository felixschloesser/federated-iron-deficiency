"""Screening models as files in the hospital's folder: what the laboratory
director sees of each, and why one cannot be deployed (features/deployment.feature)."""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import assert_never

from django.db import models
from django.utils import formats, timezone

from iron_deficiency.screening import Problem, final_model_paths, from_bytes


def model_name(stored_at: datetime | None, run_id: str) -> str:
    """How the laboratory director knows a model: when it arrived (glossary.toml, screening model)."""
    if stored_at is None:
        return f"Screening model of run {run_id}"
    return f"Screening model of {formats.date_format(timezone.localtime(stored_at), 'j M Y, H:i')}"


class CannotDeploy(models.TextChoices):
    UNREADABLE = "unreadable", "not a readable model file"
    FEATURES_DIFFER = "features_differ", "trained on other features"
    LOCAL_VALIDATION_MISSING = "local_validation_missing", "no local validation"
    STANDARDIZATION_MISSING = "standardization_missing", "no standardization"

    @classmethod
    def because(cls, problem: Problem) -> "CannotDeploy":
        match problem:
            case Problem.UNREADABLE:
                return cls.UNREADABLE
            case Problem.FEATURES_DIFFER:
                return cls.FEATURES_DIFFER
            case Problem.LOCAL_VALIDATION_MISSING:
                return cls.LOCAL_VALIDATION_MISSING
            case Problem.STANDARDIZATION_MISSING:
                return cls.STANDARDIZATION_MISSING
            case _:
                assert_never(problem)


@dataclass(frozen=True)
class Ratio:
    """Part of a whole, shown with both counts: 7 of 10."""

    part: int
    whole: int

    def __str__(self) -> str:
        return f"{self.part} of {self.whole}"

    @property
    def percent(self) -> str | None:
        """The share as a whole percentage; None when there is no whole."""
        return f"{self.part / self.whole:.0%}" if self.whole else None


@dataclass(frozen=True)
class LocalValidationAt:
    """A screening model's local validation at one threshold: its confusion matrix."""

    threshold: float
    counts: dict[str, int]

    def count(self, cell: str) -> int:
        """One cell of the confusion matrix."""
        return int(self.counts.get(cell, 0))

    # The laboratory's measures of a method's ability to detect disease (WHO LQMS
    # 3-3, p. 40), each as the counts it comes from.
    @property
    def sensitivity(self) -> "Ratio":
        found = self.count("true_positives")
        return Ratio(found, found + self.count("false_negatives"))

    @property
    def specificity(self) -> "Ratio":
        cleared = self.count("true_negatives")
        return Ratio(cleared, cleared + self.count("false_positives"))

    @property
    def positive_predictive_value(self) -> "Ratio":
        found = self.count("true_positives")
        return Ratio(found, found + self.count("false_positives"))

    @property
    def negative_predictive_value(self) -> "Ratio":
        cleared = self.count("true_negatives")
        return Ratio(cleared, cleared + self.count("false_negatives"))


@dataclass(frozen=True)
class ScreeningModelFile:
    """A screening model as its file says, and why it cannot be deployed, if it cannot."""

    run_id: str
    problem: CannotDeploy | None
    stored_at: datetime | None = None
    federated_auroc: float | None = None
    local_auroc: float | None = None
    # One row per threshold the laboratory director may deploy at, lowest first.
    local_validation: list[LocalValidationAt] = field(default_factory=list)

    @property
    def name(self) -> str:
        return model_name(self.stored_at, self.run_id)

    def at(self, threshold: float) -> LocalValidationAt | None:
        """The local validation at a threshold; None if the file holds none there."""
        return next(
            (row for row in self.local_validation if row.threshold == threshold), None
        )


def screening_model_file(run_id: str, data: bytes) -> ScreeningModelFile:
    """A screening model as the laboratory director sees it, from its file's bytes."""
    model = from_bytes(data)
    problem = model.problem()
    return ScreeningModelFile(
        run_id=run_id,
        problem=None if problem is None else CannotDeploy.because(problem),
        stored_at=model.stored_at,
        federated_auroc=model.federated.get("eval_auroc"),
        local_auroc=model.local_auroc,
        local_validation=[
            LocalValidationAt(threshold, counts)
            for threshold, counts in sorted(model.confusion_matrices.items())
        ],
    )


def screening_models(directory: Path | None) -> list[ScreeningModelFile]:
    """Every screening model in the hospital's folder, newest first."""
    if directory is None or not directory.is_dir():
        return []
    files = [
        screening_model_file(path.stem, path.read_bytes())
        for path in final_model_paths(directory)
    ]
    return sorted(
        files,
        key=lambda file: (file.stored_at is not None, file.stored_at),
        reverse=True,
    )


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
