"""Centralized baseline: train on the hospitals' pooled training splits."""

import tomllib
from pathlib import Path

import torch
from torch.utils.data import ConcatDataset, DataLoader

from iron_deficiency.dataset import load_federated_dataset
from iron_deficiency.task import SEED, Net, load_data, train

# Same hyperparameters as the federated run
CONFIG = tomllib.loads(Path("pyproject.toml").read_text())["tool"]["flwr"]["app"]["config"]


def train_centralized(seed: int, num_hospitals: int = 3) -> dict[str, torch.Tensor]:
    """Return weights trained on the union of the hospitals' training splits.

    Each row keeps its own hospital's standardization, as in federated training,
    so pooling the training instead of averaging updates is the only difference.
    """
    fds = load_federated_dataset()
    trainsets = [
        load_data(fds.load_partition(i).to_pandas(), CONFIG["batch-size"])[0].dataset
        for i in range(num_hospitals)
    ]
    trainloader = DataLoader(
        ConcatDataset(trainsets),
        batch_size=CONFIG["batch-size"],
        shuffle=True,
        generator=torch.Generator().manual_seed(SEED),
    )
    # Same device choice as the ClientApp
    device = torch.device(
        "cuda"
        if torch.cuda.is_available()
        else "mps"
        if torch.backends.mps.is_available()
        else "cpu"
    )

    # Same seed as the ServerApp, so both arms start from the same weights
    torch.manual_seed(seed)
    model = Net()
    # Federated training sees every row once per round, so match the total epochs.
    train(
        model,
        trainloader,
        epochs=CONFIG["num-server-rounds"] * CONFIG["local-epochs"],
        lr=CONFIG["learning-rate"],
        weight_decay=CONFIG["weight-decay"],
        device=device,
    )
    return {name: tensor.cpu() for name, tensor in model.state_dict().items()}
