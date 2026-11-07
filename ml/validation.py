"""A cohort's split into training, validation and test rows, its
standardization, and evaluating a model on a split. Training and validation
split alike because both split here."""

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
    """A cohort's training, validation and test rows: 64/16/20."""

    train: Part
    validation: Part
    test: Part


class Evaluation(NamedTuple):
    """A model on one split: mean BCE loss, AUROC, and each row's probability
    beside its label."""

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
    # This cohort's training split only: no statistic leaves the hospital. As
    # Flower's tabular example fits its scaler per client; pooled standardization
    # measured no better here (2026-11-07), as FedBN argues for local statistics.
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
    """A loader for each split of a cohort; only the training one shuffles."""
    datasets = _split_cohort(cohort, seed)
    generator = torch.Generator().manual_seed(seed)
    return Splits(
        DataLoader(
            datasets.train, batch_size=batch_size, shuffle=True, generator=generator
        ),
        DataLoader(datasets.validation, batch_size=256),
        DataLoader(datasets.test, batch_size=256),
    )


@torch.no_grad()
def evaluate(net: nn.Module, dataloader: Loader) -> Evaluation:
    """The model on every row of a loader."""
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
    """The weights on the cohort's test split: a run reports its validation
    split each round and its final model is chosen by that, so only the test
    split is unseen."""
    net = Net()
    net.load_state_dict(state_dict)
    return evaluate(net, load_data(cohort).test)


def confusion_matrices(
    state_dict: dict[str, torch.Tensor],
    cohort: pd.DataFrame,
    thresholds: Iterable[float],
) -> dict[float, dict[str, int]]:
    """The weights' confusion matrix at each threshold, on the cohort's test
    split: a row is positive at a probability at or above it."""
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
