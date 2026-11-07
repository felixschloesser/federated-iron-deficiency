"""Screening models as files in the hospital's folder: storing a fetched final
model with this hospital's standardization and local validation, what the
laboratory director sees of each, and why one cannot be deployed
(features/hospital/deployment.feature)."""

import hashlib
import math
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import assert_never

import pandas as pd
import torch
from django.db import models
from django.utils import formats, timezone

from ml.final_model import (
    FinalModel,
    Problem,
    final_model_path,
    final_model_paths,
    from_bytes,
    read,
    standardization_tensor,
    write,
)
from ml.validation import auroc, confusion_matrices, standardization

# The thresholds a laboratory director chooses from: local validation counts
# at every one.
THRESHOLDS = tuple(step / 20 for step in range(1, 20))


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

    @property
    def interval(self) -> str | None:
        """The share's 95% confidence interval in whole percentages, 40–89%;
        None when there is no whole."""
        if not self.whole:
            return None
        # Wilson's score interval: unlike share ± 1.96 standard errors, it stays
        # within 0–100% and does not shrink to nothing at 0 of 10 or 10 of 10.
        z_squared = 1.96**2
        share = self.part / self.whole
        centre = (share + z_squared / (2 * self.whole)) / (1 + z_squared / self.whole)
        half = (
            math.sqrt(
                share * (1 - share) / self.whole + z_squared / (4 * self.whole**2)
            )
            * 1.96
            / (1 + z_squared / self.whole)
        )
        lower, upper = max(centre - half, 0.0), min(centre + half, 1.0)
        return f"{lower * 100:.0f}–{upper * 100:.0f}%"


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

    @property
    def local_auroc_interval(self) -> str | None:
        """The AUROC here's 95% confidence interval, 0.68–1.00; None without an
        AUROC or the counts it was measured on."""
        if self.local_auroc is None or not self.local_validation:
            return None
        # Every threshold's counts hold the same past patients.
        counts = self.local_validation[0]
        deficient = counts.count("true_positives") + counts.count("false_negatives")
        other = counts.count("true_negatives") + counts.count("false_positives")
        if not deficient or not other:
            return None
        # Hanley and McNeil's standard error (Radiology 1982;143:29–36): from the
        # AUROC and the two groups' sizes alone, which is all the file holds.
        area = self.local_auroc
        q1, q2 = area / (2 - area), 2 * area**2 / (1 + area)
        error = math.sqrt(
            (
                area * (1 - area)
                + (deficient - 1) * (q1 - area**2)
                + (other - 1) * (q2 - area**2)
            )
            / (deficient * other)
        )
        lower, upper = max(area - 1.96 * error, 0.0), min(area + 1.96 * error, 1.0)
        return f"{lower:.2f}–{upper:.2f}"


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


def store_screening_model(
    directory: Path,
    *,
    run_id: int,
    state_dict: dict[str, torch.Tensor],
    cohort: pd.DataFrame,
    federated: dict[str, float],
    stored_at: datetime,
) -> Path:
    """Store a fetched final model as a screening model, with this hospital's
    standardization and its local validation on the training cohort. `federated`
    is what the ServerApp aggregated; no other hospital's metrics reach the
    file. One is never overwritten."""
    path = final_model_path(directory, run_id)
    if path.exists():
        raise FileExistsError(path)
    mean, std = standardization(cohort)
    write(
        path,
        FinalModel(
            state_dict=state_dict,
            mean=standardization_tensor(mean),
            std=standardization_tensor(std),
            run_id=run_id,
            stored_at=stored_at,
            federated=federated,
            confusion_matrices=confusion_matrices(state_dict, cohort, THRESHOLDS),
            local_auroc=auroc(state_dict, cohort),
        ),
    )
    return path


def store_fetched(
    directory: Path,
    *,
    run_id: int,
    state_dict: dict[str, torch.Tensor],
    cohort: pd.DataFrame,
    federated: dict[str, float],
    stored_at: datetime,
) -> Path:
    """Store a fetched final model; one fetched again is kept as it was. Other
    weights under a stored run's ID are refused."""
    path = final_model_path(directory, run_id)
    if path.exists():
        stored = read(path).state_dict
        same = (
            stored is not None
            and stored.keys() == state_dict.keys()
            and all(torch.equal(stored[name], state_dict[name]) for name in state_dict)
        )
        if not same:
            raise FileExistsError(f"{path} holds other weights.")
        return path
    return store_screening_model(
        directory,
        run_id=run_id,
        state_dict=state_dict,
        cohort=cohort,
        federated=federated,
        stored_at=stored_at,
    )
