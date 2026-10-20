"""Model, data loading, training, and evaluation utilities."""

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split
from torch import nn
from torch.utils.data import DataLoader, Dataset

from iron_deficiency.dataset import FEATURES

SEED = 42


class TabularDataset(Dataset):
    """A float32 feature matrix and float32 binary labels."""

    def __init__(self, features: np.ndarray, labels: np.ndarray) -> None:
        self.X = torch.from_numpy(features)
        self.y = torch.from_numpy(labels)

    def __len__(self) -> int:
        return len(self.y)

    def __getitem__(self, index: int) -> tuple[torch.Tensor, torch.Tensor]:
        return self.X[index], self.y[index]


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

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x).squeeze(-1)


def _split_cycle(
    dataframe: pd.DataFrame, seed: int
) -> tuple[TabularDataset, TabularDataset, TabularDataset]:
    # Match the notebook's 64/16/20 split, stratified on the binary label.
    train_df, test_df = train_test_split(
        dataframe,
        test_size=0.20,
        stratify=dataframe["iron_deficient"],
        random_state=seed,
    )
    train_df, val_df = train_test_split(
        train_df,
        test_size=0.20,
        stratify=train_df["iron_deficient"],
        random_state=seed,
    )

    # Use training statistics from this cycle only, as in the notebook.
    mean = train_df[FEATURES].mean()
    std = train_df[FEATURES].std().replace(0, 1.0)

    def to_dataset(frame: pd.DataFrame) -> TabularDataset:
        features = ((frame[FEATURES] - mean) / std).values.astype(np.float32)
        labels = frame["iron_deficient"].values.astype(np.float32)
        return TabularDataset(features, labels)

    return to_dataset(train_df), to_dataset(val_df), to_dataset(test_df)


def load_data(
    cohort: pd.DataFrame,
    batch_size: int = 64,
    seed: int = SEED,
) -> tuple[DataLoader, DataLoader, DataLoader]:
    """Return train, validation, and test loaders for one cycle's cohort."""
    trainset, valset, testset = _split_cycle(cohort, seed)
    generator = torch.Generator().manual_seed(seed)
    return (
        DataLoader(trainset, batch_size=batch_size, shuffle=True, generator=generator),
        DataLoader(valset, batch_size=256),
        DataLoader(testset, batch_size=256),
    )


def train(
    net: nn.Module,
    trainloader: DataLoader,
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


@torch.no_grad()
def test(
    net: nn.Module,
    dataloader: DataLoader,
    device: torch.device | None = None,
) -> tuple[float, dict[str, float], np.ndarray, np.ndarray]:
    """Return loss, AUROC, probabilities, and labels, matching the notebook."""
    device = device or torch.device("cpu")
    net.to(device).eval()
    criterion = nn.BCEWithLogitsLoss()
    total, num_examples = 0.0, 0
    probabilities, all_labels = [], []

    for features, labels in dataloader:
        features, labels = features.to(device), labels.to(device)
        logits = net(features)
        total += criterion(logits, labels).item() * len(labels)
        num_examples += len(labels)
        probabilities.append(torch.sigmoid(logits).cpu().numpy())
        all_labels.append(labels.cpu().numpy())

    probs = np.concatenate(probabilities)
    labels = np.concatenate(all_labels)
    metrics = {"auroc": float(roc_auc_score(labels, probs))}
    return total / num_examples, metrics, probs, labels
