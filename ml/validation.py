"""Split a cohort into training, validation and test rows, standardize it, and
evaluate a model on a split. Training and validation both use this module, so
they always split a cohort the same way."""

from collections.abc import Iterable
from typing import NamedTuple

import numpy as np
import numpy.typing as npt
import pandas as pd
import torch
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split
from torch import nn
from torch.utils.data import DataLoader, Dataset

from ml.cohort import FEATURES
from ml.final_model import Net

SEED = 42


Batch = tuple[torch.Tensor, torch.Tensor]


Loader = DataLoader[Batch]


class TabularDataset(Dataset[Batch]):
    """A float32 feature matrix and float32 binary labels."""

    def __init__(
        self, features: npt.NDArray[np.float32], labels: npt.NDArray[np.float32]
    ) -> None:
        self.features = torch.from_numpy(features)
        self.labels = torch.from_numpy(labels)

    def __len__(self) -> int:
        return len(self.labels)

    def __getitem__(self, index: int) -> Batch:
        return self.features[index], self.labels[index]


class Splits[Part](NamedTuple):
    """A cohort's training, validation and test rows, split 64/16/20."""

    train: Part
    validation: Part
    test: Part


class Evaluation(NamedTuple):
    """A model's results on one split: mean BCE loss, AUROC, and each row's
    probability next to its label."""

    loss: float
    auroc: float
    probabilities: npt.NDArray[np.float32]
    labels: npt.NDArray[np.float32]


def _split_frames(dataframe: pd.DataFrame, seed: int) -> Splits[pd.DataFrame]:
    # Stratified on the binary label, so every split holds both classes.
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
    return Splits(train_df, val_df, test_df)


def _training_stats(train_df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    # Computed from this hospital's training split only, so no statistic leaves
    # the hospital. Flower's tabular example also fits its scaler per client;
    # pooled standardization measured no better here (2026-11-07), and FedBN
    # argues for local statistics too.
    return train_df[FEATURES].mean(), train_df[FEATURES].std().replace(0, 1.0)


def standardization(
    cohort: pd.DataFrame, seed: int = SEED
) -> tuple[pd.Series, pd.Series]:
    """The feature mean and std of a cohort's training split."""
    return _training_stats(_split_frames(cohort, seed).train)


def _split_cohort(dataframe: pd.DataFrame, seed: int) -> Splits[TabularDataset]:
    frames = _split_frames(dataframe, seed)
    mean, std = _training_stats(frames.train)

    def to_dataset(frame: pd.DataFrame) -> TabularDataset:
        # copy=True: pandas 3 may return a read-only view, which torch.from_numpy warns about.
        features = ((frame[FEATURES] - mean) / std).to_numpy(
            dtype=np.float32, copy=True
        )
        labels = frame["iron_deficient"].to_numpy(dtype=np.float32, copy=True)
        return TabularDataset(features, labels)

    return Splits(*(to_dataset(frame) for frame in frames))


def load_data(
    cohort: pd.DataFrame,
    batch_size: int = 64,
    seed: int = SEED,
) -> Splits[Loader]:
    """A loader for each split of a cohort; only the training one shuffles. It
    also drops each epoch's last, smaller batch, so no training step averages
    fewer than `batch_size` records."""
    datasets = _split_cohort(cohort, seed)
    generator = torch.Generator().manual_seed(seed)
    return Splits(
        DataLoader(
            datasets.train,
            batch_size=batch_size,
            shuffle=True,
            generator=generator,
            drop_last=True,
        ),
        DataLoader(datasets.validation, batch_size=256),
        DataLoader(datasets.test, batch_size=256),
    )


@torch.no_grad()
def evaluate(net: nn.Module, dataloader: Loader) -> Evaluation:
    """Evaluate the model on every row of a loader."""
    net.eval()
    criterion = nn.BCEWithLogitsLoss()
    total, num_examples = 0.0, 0
    probabilities, all_labels = [], []

    for features, labels in dataloader:
        logits = net(features)
        total += criterion(logits, labels).item() * len(labels)
        num_examples += len(labels)
        probabilities.append(torch.sigmoid(logits).numpy())
        all_labels.append(labels.numpy())

    probs = np.concatenate(probabilities)
    labels = np.concatenate(all_labels)
    return Evaluation(
        total / num_examples, float(roc_auc_score(labels, probs)), probs, labels
    )


def _held_out(state_dict: dict[str, torch.Tensor], cohort: pd.DataFrame) -> Evaluation:
    """Evaluate the weights on the cohort's test split. A run reports the
    validation split every round and its final model is chosen by it, so only
    the test split is unseen."""
    net = Net()
    net.load_state_dict(state_dict)
    return evaluate(net, load_data(cohort).test)


def confusion_matrices(
    state_dict: dict[str, torch.Tensor],
    cohort: pd.DataFrame,
    thresholds: Iterable[float],
) -> dict[float, dict[str, int]]:
    """The weights' confusion matrix at each threshold on the cohort's test
    split. A row counts as positive when its probability is at or above the
    threshold."""
    evaluation = _held_out(state_dict, cohort)
    actual = evaluation.labels == 1
    matrices = {}
    for threshold in thresholds:
        predicted = evaluation.probabilities >= threshold
        matrices[threshold] = {
            "true_positives": int((predicted & actual).sum()),
            "false_negatives": int((~predicted & actual).sum()),
            "false_positives": int((predicted & ~actual).sum()),
            "true_negatives": int((~predicted & ~actual).sum()),
        }
    return matrices


def auroc(state_dict: dict[str, torch.Tensor], cohort: pd.DataFrame) -> float:
    """The weights' AUROC on the cohort's test split."""
    return _held_out(state_dict, cohort).auroc
