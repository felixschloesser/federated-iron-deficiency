"""Local screening of new blood counts with the deployed model, and the final
model's file: the one format the ClientApp writes and every reader reads."""

import argparse
import enum
import io
import os
import pickle
import tempfile
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd
import torch

from ml.cohort import CBC_VARS, FEATURES, eligible
from ml.task import Net

# One lab export row: sample ID, registered sex, age, and the 13 CBC values.
COLUMNS = ["sample_id", "sex", "age", *CBC_VARS]

# The thresholds a laboratory director chooses from: each hospital counts its
# local validation at every one (features/deployment.feature).
THRESHOLDS = tuple(step / 20 for step in range(1, 20))

# What torch.load raises on a file that is no model file, or none it loads safely.
UNREADABLE_ERRORS = (
    pickle.UnpicklingError,
    RuntimeError,
    EOFError,
    ValueError,
    zipfile.BadZipFile,
)


class Problem(enum.Enum):
    """Why a final model's file cannot screen: the first that applies."""

    UNREADABLE = "unreadable"
    FEATURES_DIFFER = "features_differ"
    LOCAL_VALIDATION_MISSING = "local_validation_missing"
    STANDARDIZATION_MISSING = "standardization_missing"


@dataclass(frozen=True)
class FinalModel:
    """A final model as its file holds it; any part may be missing from an old or
    damaged file, which problem() then names."""

    state_dict: dict[str, torch.Tensor] | None = None
    # This hospital's standardization, in FEATURES order.
    mean: torch.Tensor | None = None
    std: torch.Tensor | None = None
    run_id: int | str | None = None
    stored_at: datetime | None = None
    # Only what the ServerApp aggregated; no other hospital's metrics (features/final_models.feature).
    federated: dict[str, float] = field(default_factory=dict)
    # Local validation: the confusion matrix at each threshold, and AUROC.
    confusion_matrices: dict[float, dict[str, int]] = field(default_factory=dict)
    local_auroc: float | None = None
    # The startup's copy only: the training parameters the run was configured with.
    run_configuration: dict[str, int | float] = field(default_factory=dict)

    def problem(self) -> Problem | None:
        if self.state_dict is None:
            return Problem.UNREADABLE
        try:
            Net().load_state_dict(self.state_dict)
        except RuntimeError:
            return Problem.FEATURES_DIFFER
        if not self.confusion_matrices:
            return Problem.LOCAL_VALIDATION_MISSING
        if self.mean is None or self.std is None:
            return Problem.STANDARDIZATION_MISSING
        return None

    def probabilities(self, features: pd.DataFrame) -> npt.NDArray[np.float32]:
        """Each row's probability of iron deficiency, from unstandardized FEATURES."""
        if self.state_dict is None or self.mean is None or self.std is None:
            raise ValueError(f"This final model cannot screen: {self.problem()}")
        net = Net()
        net.load_state_dict(self.state_dict)
        net.eval()
        x = torch.tensor(features[FEATURES].values, dtype=torch.float32)
        with torch.no_grad():
            probabilities: npt.NDArray[np.float32] = torch.sigmoid(
                net((x - self.mean) / self.std)
            ).numpy()
        return probabilities


def standardization_tensor(values: pd.Series) -> torch.Tensor:
    """A standardization's mean or std as the file holds it, in FEATURES order."""
    return torch.tensor(values[FEATURES].values, dtype=torch.float32)


def final_model_path(directory: Path, run_id: int | str) -> Path:
    """One file per training run, named after it."""
    return directory / f"{run_id}.pt"


def final_model_paths(directory: Path) -> list[Path]:
    """The final models in a folder: only files named after a run, as
    final_model_path names them; any other file there is not one."""
    return [path for path in directory.glob("*.pt") if path.stem.isdigit()]


def file_contents(model: FinalModel) -> dict[str, Any]:
    """What the file holds of a final model; parts it lacks, or holds empty, are
    left out."""
    held: dict[str, Any] = {
        "state_dict": model.state_dict,
        "mean": model.mean,
        "std": model.std,
        "run_id": model.run_id,
        "stored_at": model.stored_at.isoformat() if model.stored_at else None,
        "federated": model.federated,
        "confusion_matrices": model.confusion_matrices,
        "local_auroc": model.local_auroc,
        "run_configuration": model.run_configuration,
    }
    return {
        key: value
        for key, value in held.items()
        if value is not None and not (isinstance(value, dict) and not value)
    }


def to_bytes(model: FinalModel) -> bytes:
    """A final model in the one file format, as bytes."""
    buffer = io.BytesIO()
    torch.save(file_contents(model), buffer)
    return buffer.getvalue()


def write(path: Path, model: FinalModel) -> None:
    """Store a final model; one is never overwritten (features/final_models.feature)."""
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Written beside it under a name of its own, then linked: a reader of the
    # folder never sees half a file, "*.pt" never matches the partial one, and of
    # two writers at once the second fails, as link never replaces a file.
    descriptor, name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".partial"
    )
    os.close(descriptor)
    partial = Path(name)
    try:
        torch.save(file_contents(model), partial)
        os.link(partial, path)
    finally:
        partial.unlink(missing_ok=True)


def from_bytes(data: bytes) -> FinalModel:
    """A final model from its file's bytes; an unreadable file gives an empty one."""
    try:
        contents = torch.load(io.BytesIO(data))
    except UNREADABLE_ERRORS:
        return FinalModel()
    if not isinstance(contents, dict):
        return FinalModel()
    stored_at = contents.get("stored_at")
    local_auroc = contents.get("local_auroc")
    # An older file's single "threshold" and "local_validation" are not read: it
    # has no local validation at the thresholds a director chooses from.
    return FinalModel(
        state_dict=contents.get("state_dict"),
        mean=contents.get("mean"),
        std=contents.get("std"),
        run_id=contents.get("run_id"),
        stored_at=datetime.fromisoformat(stored_at) if stored_at else None,
        federated=dict(contents.get("federated", {})),
        confusion_matrices={
            float(threshold): dict(counts)
            for threshold, counts in contents.get("confusion_matrices", {}).items()
        },
        local_auroc=float(local_auroc) if local_auroc is not None else None,
        run_configuration=dict(contents.get("run_configuration", {})),
    )


def read(path: Path) -> FinalModel:
    return from_bytes(path.read_bytes())


def score(samples: pd.DataFrame, model: FinalModel) -> pd.Series:
    """Return the eligible samples' probabilities of iron deficiency."""
    features = samples[CBC_VARS].assign(RIDAGEYR=samples["age"])[FEATURES]
    scored = eligible(samples["sex"], samples["age"]) & features.notna().all(axis=1)
    probabilities = model.probabilities(features[scored])
    return pd.Series(probabilities, index=samples.index[scored])


def suggests_ferritin(
    cbc: Mapping[str, float], age: int, model: FinalModel, threshold: float
) -> bool:
    """Whether the model scores one CBC at or above the threshold it was deployed
    at. Who is screened is the caller's decision (features/screening.feature)."""
    features = pd.DataFrame([{**cbc, "RIDAGEYR": age}], columns=FEATURES)
    if features.isna().any(axis=None):
        raise ValueError("A CBC without all its values cannot be screened.")
    return bool(model.probabilities(features)[0] >= threshold)


def screen(samples: pd.DataFrame, model: FinalModel, threshold: float) -> pd.DataFrame:
    """Return each sample's screening result: ferritin suggested, ferritin not
    suggested, or not screened."""
    probabilities = score(samples, model)
    result = pd.Series("not screened", index=samples.index)
    result[probabilities.index] = np.where(
        probabilities >= threshold, "ferritin suggested", "ferritin not suggested"
    )

    # Only the sample ID and the decision leave: no score, no other input column.
    return pd.DataFrame({"sample_id": samples["sample_id"], "result": result})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Screen a lab export of new blood counts with the deployed model."
    )
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--threshold", type=float, required=True, help="the deployed threshold"
    )
    args = parser.parse_args()

    results = screen(
        pd.read_csv(args.input, usecols=COLUMNS), read(args.model), args.threshold
    )
    results.to_csv(args.output, index=False)
    # Print counts only, so no sample ID ends up in the terminal or its logs.
    print(results["result"].value_counts().to_string())
