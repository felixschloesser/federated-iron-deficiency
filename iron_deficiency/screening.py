"""Local screening of new blood counts with the deployed model, and the final
model's file: the one format the ClientApp writes and every reader reads."""

import argparse
import enum
import io
import pickle
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

from iron_deficiency.dataset import CBC_VARS, FEATURES, eligible
from iron_deficiency.task import Net

# One lab export row: sample ID, registered sex, age, and the 13 CBC values.
COLUMNS = ["sample_id", "sex", "age", *CBC_VARS]

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
    THRESHOLD_MISSING = "threshold_missing"
    STANDARDIZATION_MISSING = "standardization_missing"


@dataclass(frozen=True)
class FinalModel:
    """A final model as its file holds it; any part may be missing from an old or
    damaged file, which problem() then names."""

    state_dict: dict[str, torch.Tensor] | None = None
    # This hospital's standardization, in FEATURES order.
    mean: torch.Tensor | None = None
    std: torch.Tensor | None = None
    threshold: float | None = None
    run_id: int | str | None = None
    stored_at: datetime | None = None
    # Only what the ServerApp aggregated; no other hospital's metrics (R20).
    federated: dict[str, float] = field(default_factory=dict)
    local_validation: dict[str, float] = field(default_factory=dict)

    def problem(self) -> Problem | None:
        if self.state_dict is None:
            return Problem.UNREADABLE
        try:
            Net().load_state_dict(self.state_dict)
        except RuntimeError:
            return Problem.FEATURES_DIFFER
        if self.threshold is None:
            return Problem.THRESHOLD_MISSING
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


def write(path: Path, model: FinalModel) -> None:
    """Store a final model; one is never overwritten (R16)."""
    if path.exists():
        raise FileExistsError(path)
    contents: dict[str, Any] = {
        "state_dict": model.state_dict,
        "mean": model.mean,
        "std": model.std,
        "threshold": model.threshold,
        "run_id": model.run_id,
        "stored_at": model.stored_at.isoformat() if model.stored_at else None,
        "federated": model.federated,
        "local_validation": model.local_validation,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {key: value for key, value in contents.items() if value is not None}, path
    )


def from_bytes(data: bytes) -> FinalModel:
    """A final model from its file's bytes; an unreadable file gives an empty one."""
    try:
        contents = torch.load(io.BytesIO(data))
    except UNREADABLE_ERRORS:
        return FinalModel()
    if not isinstance(contents, dict):
        return FinalModel()
    stored_at = contents.get("stored_at")
    threshold = contents.get("threshold")
    return FinalModel(
        state_dict=contents.get("state_dict"),
        mean=contents.get("mean"),
        std=contents.get("std"),
        threshold=float(threshold) if threshold is not None else None,
        run_id=contents.get("run_id"),
        stored_at=datetime.fromisoformat(stored_at) if stored_at else None,
        federated=dict(contents.get("federated", {})),
        local_validation=dict(contents.get("local_validation", {})),
    )


def read(path: Path) -> FinalModel:
    return from_bytes(path.read_bytes())


def score(samples: pd.DataFrame, model: FinalModel) -> tuple[pd.Series, float]:
    """Return the eligible samples' probabilities of iron deficiency, and the threshold."""
    if model.threshold is None:
        raise ValueError(f"This final model cannot screen: {model.problem()}")
    features = samples[CBC_VARS].assign(RIDAGEYR=samples["age"])[FEATURES]
    scored = eligible(samples["sex"], samples["age"]) & features.notna().all(axis=1)
    probabilities = model.probabilities(features[scored])
    return pd.Series(probabilities, index=samples.index[scored]), model.threshold


def suggests_ferritin(cbc: Mapping[str, float], age: int, model: FinalModel) -> bool:
    """Whether the model scores one CBC at or above its threshold. Who is screened
    is the caller's decision (R4)."""
    if model.threshold is None:
        raise ValueError(f"This final model cannot screen: {model.problem()}")
    features = pd.DataFrame([{**cbc, "RIDAGEYR": age}], columns=FEATURES)
    if features.isna().any(axis=None):
        raise ValueError("A CBC without all its values cannot be screened.")
    return bool(model.probabilities(features)[0] >= model.threshold)


def screen(samples: pd.DataFrame, model: FinalModel) -> pd.DataFrame:
    """Return each sample's ID and result: flagged, not flagged, or not screened."""
    probabilities, threshold = score(samples, model)
    result = pd.Series("not screened", index=samples.index)
    result[probabilities.index] = np.where(
        probabilities >= threshold, "flagged", "not flagged"
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
    args = parser.parse_args()

    results = screen(pd.read_csv(args.input, usecols=COLUMNS), read(args.model))
    results.to_csv(args.output, index=False)
    # Print counts only, so no sample ID ends up in the terminal or its logs.
    print(results["result"].value_counts().to_string())
