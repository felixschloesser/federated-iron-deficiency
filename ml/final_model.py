"""The final model: its network, and its files: the startup's copy, the weights
on the wire, and how the hospital's screening model file is written and read.
A file is read whole or not at all."""

import io
import os
import pickle
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import torch
from torch import nn

from ml.cohort import FEATURES


class Net(nn.Module):
    """MLP for binary classification on the NHANES tabular features."""

    def __init__(
        self,
        n_features: int = len(FEATURES),
        h1: int = 64,
        h2: int = 32,
        p_drop: float = 0.2,
    ) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(n_features, h1),
            nn.ReLU(),
            nn.Dropout(p_drop),
            nn.Linear(h1, h2),
            nn.ReLU(),
            nn.Dropout(p_drop),
            nn.Linear(h2, 1),
        )

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        logits: torch.Tensor = self.net(features)
        return logits.squeeze(-1)


# What torch.load raises on a file that is no model file, or none it loads safely.
UNREADABLE_ERRORS = (
    pickle.UnpicklingError,
    RuntimeError,
    EOFError,
    ValueError,
    zipfile.BadZipFile,
)

# What reading a part raises when a file lacks it or holds something else there.
MISSING_PART_ERRORS = (KeyError, TypeError, ValueError, AttributeError)


@dataclass(frozen=True)
class FinalModel:
    """A final model as the startup keeps it: every part, or no final model."""

    state_dict: dict[str, torch.Tensor]
    run_id: int
    stored_at: datetime
    # Only what the ServerApp aggregated; no hospital's own metrics.
    federated_auroc: float
    # The training parameters the run was configured with.
    run_configuration: dict[str, int | float]


def standardization_tensor(values: pd.Series) -> torch.Tensor:
    """A standardization's mean or std as the file holds it, in FEATURES order."""
    return torch.tensor(values[FEATURES].values, dtype=torch.float32)


def model_file_path(directory: Path, run_id: int | str) -> Path:
    """One file per training run, named after it."""
    return directory / f"{run_id}.pt"


def model_file_paths(directory: Path) -> list[Path]:
    """The final models in a folder: only files named after a run, as
    model_file_path names them; any other file there is not one."""
    return [path for path in directory.glob("*.pt") if path.stem.isdigit()]


def fitting_weights(state_dict: object) -> dict[str, torch.Tensor]:
    """The weights, if they fit Net(); TypeError if they do not."""
    if not isinstance(state_dict, dict):
        raise TypeError("No weights.")
    try:
        Net().load_state_dict(state_dict)
    except RuntimeError as error:
        raise TypeError("The weights do not fit the network.") from error
    return state_dict


def load_contents(data: bytes) -> dict[str, Any] | None:
    """What a file's bytes hold; None if they hold no dict torch loads safely."""
    try:
        # Never unpickle objects: the file crosses a trust boundary.
        contents = torch.load(io.BytesIO(data), weights_only=True)
    except UNREADABLE_ERRORS:
        return None
    return contents if isinstance(contents, dict) else None


def write_contents(path: Path, contents: dict[str, Any]) -> None:
    """Store a file's contents; one is never overwritten."""
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
        torch.save(contents, partial)
        os.link(partial, path)
    finally:
        partial.unlink(missing_ok=True)


def write_final_model(path: Path, model: FinalModel) -> None:
    """Store the startup's copy of a final model; one is never overwritten."""
    write_contents(
        path,
        {
            "state_dict": model.state_dict,
            "run_id": model.run_id,
            "stored_at": model.stored_at.isoformat(),
            "federated_auroc": model.federated_auroc,
            "run_configuration": model.run_configuration,
        },
    )


def read_final_model(path: Path) -> FinalModel | None:
    """The startup's copy of a final model; None if the file is unreadable, lacks
    a part, or its weights do not fit the network."""
    contents = load_contents(path.read_bytes())
    if contents is None:
        return None
    try:
        return FinalModel(
            state_dict=fitting_weights(contents["state_dict"]),
            run_id=int(contents["run_id"]),
            stored_at=datetime.fromisoformat(contents["stored_at"]),
            federated_auroc=float(contents["federated_auroc"]),
            run_configuration=dict(contents["run_configuration"]),
        )
    except MISSING_PART_ERRORS:
        return None


def weights_to_bytes(state_dict: dict[str, torch.Tensor]) -> bytes:
    """A final model's weights as they cross the wire."""
    buffer = io.BytesIO()
    torch.save(state_dict, buffer)
    return buffer.getvalue()


def weights_from_bytes(data: bytes) -> dict[str, torch.Tensor] | None:
    """Weights from the wire; None if unreadable or they do not fit the network."""
    contents = load_contents(data)
    try:
        return None if contents is None else fitting_weights(contents)
    except MISSING_PART_ERRORS:
        return None
