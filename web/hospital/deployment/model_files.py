"""Screening models as files in the hospital's folder: storing a fetched final
model with this hospital's standardization and local validation, and what the
laboratory director sees of each. A file is read whole or not at all
(features/hospital/deployment.feature)."""

import hashlib
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd
import torch
from django.utils import formats, timezone

from ml.final_model import (
    MISSING_PART_ERRORS,
    final_model_path,
    final_model_paths,
    fitting_weights,
    load_contents,
    standardization_tensor,
    write_contents,
)
from ml.validation import auroc, confusion_matrices, standardization

# The thresholds a laboratory director chooses from: local validation counts
# at every one.
THRESHOLDS = tuple(step / 20 for step in range(1, 20))

# The four cells of a confusion matrix, as the file names them.
CELLS = ("true_positives", "false_negatives", "false_positives", "true_negatives")


def model_name(stored_at: datetime) -> str:
    """How the laboratory director knows a model: when it arrived (glossary.toml, screening model)."""
    return f"Screening model of {formats.date_format(timezone.localtime(stored_at), 'j M Y, H:i')}"


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
        return self.counts[cell]

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


def auroc_interval(area: float, counts: LocalValidationAt) -> str:
    """An AUROC's 95% confidence interval, 0.68–1.00, from the past patients
    whose counts it was measured on. Neither group is ever empty: a training
    cohort holds at least 10 of each class, and the test split is stratified."""
    deficient = counts.count("true_positives") + counts.count("false_negatives")
    other = counts.count("true_negatives") + counts.count("false_positives")
    # Hanley and McNeil's standard error (Radiology 1982;143:29–36): from the
    # AUROC and the two groups' sizes alone, which is all the file holds.
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


@dataclass(frozen=True)
class ScreeningModelFile:
    """A screening model as its file holds it (glossary.toml): every part, or no
    screening model."""

    state_dict: dict[str, torch.Tensor]
    # This hospital's standardization, in FEATURES order.
    mean: torch.Tensor
    std: torch.Tensor
    run_id: str
    stored_at: datetime
    # Only what the ServerApp aggregated; no other hospital's metrics.
    federated_auroc: float
    local_auroc: float
    # One row per threshold the laboratory director may deploy at, lowest first.
    local_validation: list[LocalValidationAt]

    @property
    def name(self) -> str:
        return model_name(self.stored_at)

    def at(self, threshold: float) -> LocalValidationAt | None:
        """The local validation at a threshold; None if the file holds none there."""
        return next(
            (row for row in self.local_validation if row.threshold == threshold), None
        )

    @property
    def local_auroc_interval(self) -> str:
        """The AUROC here's 95% confidence interval."""
        # Every threshold's counts hold the same past patients.
        return auroc_interval(self.local_auroc, self.local_validation[0])


def screening_model_file(data: bytes) -> ScreeningModelFile | None:
    """A screening model from its file's bytes; None if the file is unreadable,
    lacks a part, or its weights do not fit the network."""
    contents = load_contents(data)
    if contents is None:
        return None
    try:
        local_validation = [
            LocalValidationAt(
                float(threshold), {cell: int(counts[cell]) for cell in CELLS}
            )
            for threshold, counts in sorted(contents["confusion_matrices"].items())
        ]
        return ScreeningModelFile(
            state_dict=fitting_weights(contents["state_dict"]),
            mean=contents["mean"],
            std=contents["std"],
            run_id=str(int(contents["run_id"])),
            stored_at=datetime.fromisoformat(contents["stored_at"]),
            federated_auroc=float(contents["federated_auroc"]),
            local_auroc=float(contents["local_auroc"]),
            local_validation=local_validation,
        )
    except MISSING_PART_ERRORS:
        return None


def screening_models(directory: Path | None) -> list[ScreeningModelFile]:
    """Every readable screening model in the hospital's folder, newest first."""
    if directory is None or not directory.is_dir():
        return []
    files = [
        file
        for path in final_model_paths(directory)
        if (file := screening_model_file(path.read_bytes())) is not None
    ]
    return sorted(files, key=lambda file: file.stored_at, reverse=True)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def store_screening_model(
    directory: Path,
    *,
    run_id: int,
    state_dict: dict[str, torch.Tensor],
    cohort: pd.DataFrame,
    federated_auroc: float,
    stored_at: datetime,
) -> Path:
    """Store a fetched final model as a screening model, with this hospital's
    standardization and its local validation on the training cohort.
    `federated_auroc` is what the ServerApp aggregated; no other hospital's
    metrics reach the file. One is never overwritten."""
    path = final_model_path(directory, run_id)
    if path.exists():
        raise FileExistsError(path)
    mean, std = standardization(cohort)
    write_contents(
        path,
        {
            "state_dict": state_dict,
            "mean": standardization_tensor(mean),
            "std": standardization_tensor(std),
            "run_id": run_id,
            "stored_at": stored_at.isoformat(),
            "federated_auroc": federated_auroc,
            "confusion_matrices": confusion_matrices(state_dict, cohort, THRESHOLDS),
            "local_auroc": auroc(state_dict, cohort),
        },
    )
    return path


def store_fetched(
    directory: Path,
    *,
    run_id: int,
    state_dict: dict[str, torch.Tensor],
    cohort: pd.DataFrame,
    federated_auroc: float,
    stored_at: datetime,
) -> Path:
    """Store a fetched final model; one fetched again is kept as it was. Other
    weights under a stored run's ID are refused."""
    path = final_model_path(directory, run_id)
    if path.exists():
        stored = screening_model_file(path.read_bytes())
        same = (
            stored is not None
            and stored.state_dict.keys() == state_dict.keys()
            and all(
                torch.equal(stored.state_dict[name], state_dict[name])
                for name in state_dict
            )
        )
        if not same:
            raise FileExistsError(f"{path} holds other weights.")
        return path
    return store_screening_model(
        directory,
        run_id=run_id,
        state_dict=state_dict,
        cohort=cohort,
        federated_auroc=federated_auroc,
        stored_at=stored_at,
    )
