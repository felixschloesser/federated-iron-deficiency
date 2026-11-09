"""Local training at each hospital, and storing the final model at the startup:
one file per training run, which recipient hospitals can fetch once it is
released."""

import os
from collections.abc import Mapping, Sized
from datetime import datetime
from pathlib import Path

import torch
from torch import nn

from ml.final_model import FinalModel, model_file_path, write_final_model
from ml.validation import Loader


def train(
    net: nn.Module,
    trainloader: Loader,
    epochs: int = 1,
    lr: float = 1e-3,
    weight_decay: float = 1e-4,
) -> float:
    """Train for ``epochs`` epochs and return sample-weighted mean BCE loss."""
    if len(trainloader) == 0:
        # The loader drops a last, smaller batch, so a split smaller than one
        # batch leaves nothing to train on.
        raise ValueError(
            f"The training split holds {dataset_size(trainloader)} records, fewer"
            f" than one batch of {trainloader.batch_size}."
        )
    net.train()
    criterion = nn.BCEWithLogitsLoss()
    optimiser = torch.optim.Adam(net.parameters(), lr=lr, weight_decay=weight_decay)
    total, num_examples = 0.0, 0

    for _ in range(epochs):
        for features, labels in trainloader:
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


# The run configuration keys that say how a model was trained. The run
# configuration also carries the W&B key, which is left out.
TRAINING_PARAMETERS = (
    "num-server-rounds",
    "fraction-evaluate",
    "local-epochs",
    "learning-rate",
    "weight-decay",
    "batch-size",
    "model-seed",
)


class FinalModelsFolderUnavailable(RuntimeError):
    """The ServerApp has no folder it can keep the final model in."""


def startup_final_models(environ: Mapping[str, str]) -> Path | None:
    """The startup's folder of final models: the absolute path FINAL_MODELS_DIR
    names, which the deployment creates and the ServerApp writes to. None if the
    deployment names none, as on SuperGrid, where Flower runs the ServerApp and
    the startup could not read a kept model anyway.

    Checked before training, so a run whose final model could not be kept never
    starts. The ServerApp never creates the folder, so a wrong path cannot
    quietly keep final models where the startup's web app does not look."""
    named = environ.get("FINAL_MODELS_DIR", "")
    if not named:
        return None
    folder = Path(named)
    if not (folder.is_absolute() and folder.is_dir() and os.access(folder, os.W_OK)):
        raise FinalModelsFolderUnavailable(
            f"FINAL_MODELS_DIR={named} is not an absolute path to a folder the"
            " ServerApp can write to."
        )
    return folder


def training_parameters(run_config: Mapping[str, object]) -> dict[str, int | float]:
    """Only the training parameters of a run configuration."""
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
    federated_auroc: float,
    stored_at: datetime,
    run_configuration: dict[str, int | float],
) -> Path:
    """Store the startup's copy of a training run's final model: the weights
    every hospital was sent, without any hospital's standardization or local
    validation."""
    path = model_file_path(directory, run_id)
    write_final_model(
        path,
        FinalModel(
            state_dict=state_dict,
            run_id=run_id,
            stored_at=stored_at,
            federated_auroc=federated_auroc,
            run_configuration=run_configuration,
        ),
    )
    return path
