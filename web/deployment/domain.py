"""Reading screening models from the hospital's folder, and the deployed model (R17, R19)."""

import hashlib
import pickle
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from django.db import models

from iron_deficiency.screening import fits_model, read_final_model
from web.deployment.models import Deployment, ScreeningModel, model_name

UNREADABLE_ERRORS = (
    pickle.UnpicklingError,
    RuntimeError,
    EOFError,
    ValueError,
    zipfile.BadZipFile,
)


class CannotDeploy(models.TextChoices):
    UNREADABLE = "unreadable", "not a readable model file"
    FEATURES_DIFFER = "features_differ", "trained on other features"
    THRESHOLD_MISSING = "threshold_missing", "no threshold"
    STANDARDIZATION_MISSING = "standardization_missing", "no standardization"


class NoUsableModel(models.TextChoices):
    NO_DEPLOYED_MODEL = "no_deployed_model", "No screening model is deployed"
    DEPLOYED_MODEL_CHANGED = (
        "deployed_model_changed",
        "The deployed model changed on disk since it was deployed",
    )


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

    @property
    def deficient_found(self) -> int:
        return int(self.local_validation.get("true_positives", 0))

    @property
    def deficient_total(self) -> int:
        return self.deficient_found + int(
            self.local_validation.get("false_negatives", 0)
        )

    @property
    def unnecessary_suggestions(self) -> int:
        return int(self.local_validation.get("false_positives", 0))

    @property
    def local_auroc(self) -> float | None:
        return self.local_validation.get("auroc")


def _problem(contents: dict[str, Any]) -> CannotDeploy | None:
    if "state_dict" not in contents:
        return CannotDeploy.UNREADABLE
    if not fits_model(contents["state_dict"]):
        return CannotDeploy.FEATURES_DIFFER
    if "threshold" not in contents:
        return CannotDeploy.THRESHOLD_MISSING
    if "mean" not in contents or "std" not in contents:
        return CannotDeploy.STANDARDIZATION_MISSING
    return None


def read_screening_model_file(path: Path) -> ScreeningModelFile:
    try:
        contents = read_final_model(path)
    except UNREADABLE_ERRORS:
        return ScreeningModelFile(run_id=path.stem, problem=CannotDeploy.UNREADABLE)
    if not isinstance(contents, dict):
        return ScreeningModelFile(run_id=path.stem, problem=CannotDeploy.UNREADABLE)
    stored_at = contents.get("stored_at")
    threshold = contents.get("threshold")
    return ScreeningModelFile(
        run_id=path.stem,
        problem=_problem(contents),
        stored_at=datetime.fromisoformat(stored_at) if stored_at else None,
        threshold=float(threshold) if threshold is not None else None,
        federated_auroc=contents.get("federated", {}).get("eval_auroc"),
        local_validation=dict(contents.get("local_validation", {})),
    )


def screening_models(directory: Path | None) -> list[ScreeningModelFile]:
    """Every screening model in the hospital's folder, newest first."""
    if directory is None or not directory.is_dir():
        return []
    files = [read_screening_model_file(path) for path in directory.glob("*.pt")]
    return sorted(
        files,
        key=lambda file: (file.stored_at is not None, file.stored_at),
        reverse=True,
    )


def sha256(path: Path) -> str:
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def deployed_model(
    directory: Path | None,
) -> tuple[ScreeningModel | None, NoUsableModel | None]:
    """The deployed model, and why it cannot screen if it cannot (R19)."""
    latest = (
        Deployment.objects.select_related("screening_model")
        .order_by("-deployed_at", "-pk")
        .first()
    )
    if latest is None:
        return None, NoUsableModel.NO_DEPLOYED_MODEL
    screening_model = latest.screening_model
    path = None if directory is None else directory / f"{screening_model.run_id}.pt"
    if path is None or not path.exists() or sha256(path) != screening_model.sha256:
        return screening_model, NoUsableModel.DEPLOYED_MODEL_CHANGED
    return screening_model, None
