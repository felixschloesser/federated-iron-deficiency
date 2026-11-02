"""Reading screening models from the hospital's folder, and the deployed model (R17, R19)."""

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import assert_never

from django.db import models

from iron_deficiency.screening import (
    FinalModel,
    Problem,
    final_model_path,
    from_bytes,
    suggests_ferritin,
)
from web.deployment.models import Deployment, ScreeningModel, model_name


class CannotDeploy(models.TextChoices):
    UNREADABLE = "unreadable", "not a readable model file"
    FEATURES_DIFFER = "features_differ", "trained on other features"
    THRESHOLD_MISSING = "threshold_missing", "no threshold"
    STANDARDIZATION_MISSING = "standardization_missing", "no standardization"

    @classmethod
    def because(cls, problem: Problem) -> "CannotDeploy":
        match problem:
            case Problem.UNREADABLE:
                return cls.UNREADABLE
            case Problem.FEATURES_DIFFER:
                return cls.FEATURES_DIFFER
            case Problem.THRESHOLD_MISSING:
                return cls.THRESHOLD_MISSING
            case Problem.STANDARDIZATION_MISSING:
                return cls.STANDARDIZATION_MISSING
            case _:
                assert_never(problem)


class NoUsableModel(models.TextChoices):
    NO_DEPLOYED_MODEL = "no_deployed_model", "No screening model is deployed"
    DEPLOYED_MODEL_CHANGED = (
        "deployed_model_changed",
        "The deployed model changed on disk since it was deployed",
    )


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
class ScreeningModelFile:
    """A screening model as its file says, and why it cannot be deployed, if it cannot."""

    run_id: str
    problem: CannotDeploy | None
    stored_at: datetime | None = None
    threshold: float | None = None
    federated_auroc: float | None = None
    local_validation: dict[str, float] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return model_name(self.stored_at, self.run_id)

    def count(self, cell: str) -> int:
        """One cell of the local validation's confusion matrix."""
        return int(self.local_validation.get(cell, 0))

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

    @property
    def local_auroc(self) -> float | None:
        return self.local_validation.get("auroc")


def screening_model_file(run_id: str, data: bytes) -> ScreeningModelFile:
    """A screening model as the laboratory director sees it, from its file's bytes."""
    model = from_bytes(data)
    problem = model.problem()
    return ScreeningModelFile(
        run_id=run_id,
        problem=None if problem is None else CannotDeploy.because(problem),
        stored_at=model.stored_at,
        threshold=model.threshold,
        federated_auroc=model.federated.get("eval_auroc"),
        local_validation=model.local_validation,
    )


def screening_models(directory: Path | None) -> list[ScreeningModelFile]:
    """Every screening model in the hospital's folder, newest first."""
    if directory is None or not directory.is_dir():
        return []
    files = [
        screening_model_file(path.stem, path.read_bytes())
        for path in directory.glob("*.pt")
    ]
    return sorted(
        files,
        key=lambda file: (file.stored_at is not None, file.stored_at),
        reverse=True,
    )


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class Screener:
    """The deployed model, loaded from the very bytes whose hash was checked (R19)."""

    screening_model: ScreeningModel
    final_model: FinalModel

    def suggests_ferritin(self, cbc: Mapping[str, float], age: int) -> bool:
        return suggests_ferritin(cbc, age, self.final_model)


def screener(directory: Path | None) -> Screener | NoUsableModel:
    """The deployed model ready to screen, or why there is none (R19)."""
    latest = (
        Deployment.objects.select_related("screening_model")
        .order_by("-deployed_at", "-pk")
        .first()
    )
    if latest is None:
        return NoUsableModel.NO_DEPLOYED_MODEL
    screening_model = latest.screening_model
    path = (
        None
        if directory is None
        else final_model_path(directory, screening_model.run_id)
    )
    data = path.read_bytes() if path is not None and path.is_file() else None
    if data is None or sha256(data) != screening_model.sha256:
        return NoUsableModel.DEPLOYED_MODEL_CHANGED
    return Screener(screening_model, from_bytes(data))
