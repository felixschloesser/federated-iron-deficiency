"""The model's network, and the files and bytes a final model is stored in.

Covers the startup's copy of a final model, the weights sent from the startup to
a hospital, and the helpers the hospital uses to write and read its screening
model files. A file is either read completely or rejected; a partly valid file
is never used."""

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


# The errors torch.load raises when a file is not a model file, or holds objects
# it refuses to load with weights_only=True.
UNREADABLE_ERRORS = (
    pickle.UnpicklingError,
    RuntimeError,
    EOFError,
    ValueError,
    zipfile.BadZipFile,
)

# The errors reading a field raises when the file lacks it or it holds the wrong
# type.
MISSING_PART_ERRORS = (KeyError, TypeError, ValueError, AttributeError)


@dataclass(frozen=True)
class FinalModel:
    """A final model as the startup keeps it. Every field is required: a file
    missing one is not a final model."""

    state_dict: dict[str, torch.Tensor]
    run_id: int
    stored_at: datetime
    # The AUROC the ServerApp aggregated across hospitals, never one hospital's.
    federated_auroc: float
    # The training parameters the run was configured with.
    run_configuration: dict[str, int | float]


def standardization_tensor(values: pd.Series) -> torch.Tensor:
    """A standardization's mean or std as a tensor in FEATURES order, as the
    screening model file stores it."""
    return torch.tensor(values[FEATURES].values, dtype=torch.float32)


def model_file_path(directory: Path, run_id: int | str) -> Path:
    """The path of a training run's final model file, named after its run ID."""
    return directory / f"{run_id}.pt"


def model_file_paths(directory: Path) -> list[Path]:
    """The final model files in `directory`: only files named the way
    model_file_path names them; any other file is ignored."""
    return [path for path in directory.glob("*.pt") if path.stem.isdigit()]


def fitting_weights(state_dict: object) -> dict[str, torch.Tensor]:
    """Return the weights if they fit Net(); raise TypeError otherwise."""
    if not isinstance(state_dict, dict):
        raise TypeError("No weights.")
    try:
        Net().load_state_dict(state_dict)
    except RuntimeError as error:
        raise TypeError("The weights do not fit the network.") from error
    return state_dict


def load_contents(data: bytes) -> dict[str, Any] | None:
    """The dict a file's bytes hold, or None if they hold no dict torch can load
    safely."""
    try:
        # weights_only=True: never unpickle arbitrary objects, because the bytes
        # come from another party.
        contents = torch.load(io.BytesIO(data), weights_only=True)
    except UNREADABLE_ERRORS:
        return None
    return contents if isinstance(contents, dict) else None


def write_contents(path: Path, contents: dict[str, Any]) -> None:
    """Write `contents` to `path`; fail if a file already exists there, or if
    its folder does not exist. The folder's owner creates it, never a writer,
    so a wrong path fails instead of keeping a file where no reader looks."""
    if path.exists():
        raise FileExistsError(path)
    # Write to a temporary file in the same folder, then hard-link it to its
    # final name. A reader never sees half a file, the "*.pt" glob never matches
    # the temporary one, and if two writers race, the second fails because a
    # link never replaces an existing file.
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
    """Store the startup's copy of a final model; an existing file is never
    overwritten."""
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
    """Read the startup's copy of a final model. None if the file is unreadable,
    lacks a field, or its weights do not fit the network."""
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
    """Serialize a final model's weights to send to a hospital."""
    buffer = io.BytesIO()
    torch.save(state_dict, buffer)
    return buffer.getvalue()


def weights_from_bytes(data: bytes) -> dict[str, torch.Tensor] | None:
    """Deserialize weights received from the startup; None if they are unreadable
    or do not fit the network."""
    contents = load_contents(data)
    try:
        return None if contents is None else fitting_weights(contents)
    except MISSING_PART_ERRORS:
        return None
