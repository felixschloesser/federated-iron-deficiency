"""Training at each hospital, and the final model as the startup keeps it: one
file per training run, which recipient hospitals fetch once it is released."""

from collections.abc import Mapping, Sized
from datetime import UTC, datetime
from pathlib import Path

import torch
from torch import nn

from ml.dataset import CYCLES, HOSPITALS, hospital_slug
from ml.final_model import (
    FinalModel,
    final_model_path,
    final_model_paths,
    read,
    write,
)
from ml.validation import Loader


def train(
    net: nn.Module,
    trainloader: Loader,
    epochs: int = 1,
    lr: float = 1e-3,
    weight_decay: float = 1e-4,
    device: torch.device | None = None,
    optimiser: torch.optim.Optimizer | None = None,
) -> float:
    """Train for ``epochs`` epochs and return sample-weighted mean BCE loss."""
    device = device or torch.device("cpu")
    net.to(device).train()
    criterion = nn.BCEWithLogitsLoss()
    optimiser = optimiser or torch.optim.Adam(
        net.parameters(), lr=lr, weight_decay=weight_decay
    )
    total, num_examples = 0.0, 0

    for _ in range(epochs):
        for features, labels in trainloader:
            features, labels = features.to(device), labels.to(device)
            optimiser.zero_grad()
            loss = criterion(net(features), labels)
            loss.backward()
            optimiser.step()
            total += loss.item() * len(labels)
            num_examples += len(labels)

    return total / num_examples


def dataset_size(loader: Loader) -> int:
    """Return the number of rows in a loader's dataset."""
    if not isinstance(loader.dataset, Sized):
        raise TypeError("The loader's dataset has no length")
    return len(loader.dataset)


# The run configuration that says how a model was trained; never the folder it
# was kept in nor the W&B key, which the run configuration also carries.
TRAINING_PARAMETERS = (
    "num-server-rounds",
    "fraction-evaluate",
    "local-epochs",
    "learning-rate",
    "weight-decay",
    "batch-size",
    "model-seed",
)

# Where final models live when no demo directory is configured.
DEFAULT_DEMO_DIR = Path.home() / ".cache" / "iron-deficiency"


def hospital_screening_models(demo_dir: Path, partition_id: int) -> Path:
    """The screening-models folder of the hospital that holds this partition."""
    cycle = list(CYCLES)[partition_id]  # Partition IDs follow CYCLES order
    return demo_dir / "hospitals" / hospital_slug(HOSPITALS[cycle]) / "screening-models"


def startup_final_models(demo_dir: Path) -> Path:
    """The startup's own copy of every final model (report DS4)."""
    return demo_dir / "startup" / "final-models"


def training_parameters(run_config: Mapping[str, object]) -> dict[str, int | float]:
    """The training parameters of a run configuration, and nothing else of it."""
    return {
        key: value
        for key, value in run_config.items()
        if key in TRAINING_PARAMETERS and isinstance(value, (int, float))
    }


def keep_final_model(
    directory: Path,
    *,
    run_id: int,
    state_dict: dict[str, torch.Tensor],
    federated: dict[str, float],
    stored_at: datetime,
    run_configuration: dict[str, int | float] | None = None,
) -> Path:
    """Keep the startup's copy of a training run's final model (DS4): what every
    hospital was sent, without any hospital's standardization or validation."""
    path = final_model_path(directory, run_id)
    write(
        path,
        FinalModel(
            state_dict=state_dict,
            run_id=run_id,
            stored_at=stored_at,
            federated=federated,
            run_configuration=run_configuration or {},
        ),
    )
    return path


def latest_final_model(directory: Path) -> Path:
    """The final model stored last in a folder."""
    unknown = datetime.min.replace(tzinfo=UTC)
    return max(
        final_model_paths(directory), key=lambda path: read(path).stored_at or unknown
    )
