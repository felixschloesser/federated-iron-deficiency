"""Local validation: how a hospital checks a final model on its own cohort
before it may deploy it, and stores it with that validation. The cohort's split
and standardization live here too, so training and validation split alike."""

from datetime import datetime
from pathlib import Path

import numpy as np
import numpy.typing as npt
import pandas as pd
import torch
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split
from torch import nn
from torch.utils.data import DataLoader, Dataset

from ml.cohort import FEATURES
from ml.final_model import (
    THRESHOLDS,
    FinalModel,
    Net,
    final_model_path,
    read,
    standardization_tensor,
    write,
)

SEED = 42


Batch = tuple[torch.Tensor, torch.Tensor]


Loader = DataLoader[Batch]


class TabularDataset(Dataset[Batch]):
    """A float32 feature matrix and float32 binary labels."""

    def __init__(
        self, features: npt.NDArray[np.float32], labels: npt.NDArray[np.float32]
    ) -> None:
        self.X = torch.from_numpy(features)
        self.y = torch.from_numpy(labels)

    def __len__(self) -> int:
        return len(self.y)

    def __getitem__(self, index: int) -> Batch:
        return self.X[index], self.y[index]


def _split_frames(
    dataframe: pd.DataFrame, seed: int
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
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
    return train_df, val_df, test_df


def _training_stats(train_df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    # Use training statistics from this cycle only, as in the notebook.
    return train_df[FEATURES].mean(), train_df[FEATURES].std().replace(0, 1.0)


def standardization(
    cohort: pd.DataFrame, seed: int = SEED
) -> tuple[pd.Series, pd.Series]:
    """Return the feature mean and std of one cycle's training split."""
    return _training_stats(_split_frames(cohort, seed)[0])


def _split_cycle(
    dataframe: pd.DataFrame, seed: int
) -> tuple[TabularDataset, TabularDataset, TabularDataset]:
    train_df, val_df, test_df = _split_frames(dataframe, seed)
    mean, std = _training_stats(train_df)

    def to_dataset(frame: pd.DataFrame) -> TabularDataset:
        # copy=True: pandas 3 may return a read-only view, which torch.from_numpy warns about.
        features = ((frame[FEATURES] - mean) / std).to_numpy(
            dtype=np.float32, copy=True
        )
        labels = frame["iron_deficient"].to_numpy(dtype=np.float32, copy=True)
        return TabularDataset(features, labels)

    return to_dataset(train_df), to_dataset(val_df), to_dataset(test_df)


def load_data(
    cohort: pd.DataFrame,
    batch_size: int = 64,
    seed: int = SEED,
) -> tuple[Loader, Loader, Loader]:
    """Return train, validation, and test loaders for one cycle's cohort."""
    trainset, valset, testset = _split_cycle(cohort, seed)
    generator = torch.Generator().manual_seed(seed)
    return (
        DataLoader(trainset, batch_size=batch_size, shuffle=True, generator=generator),
        DataLoader(valset, batch_size=256),
        DataLoader(testset, batch_size=256),
    )


@torch.no_grad()
def evaluate(
    net: nn.Module,
    dataloader: Loader,
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


def local_validation(
    state_dict: dict[str, torch.Tensor], cohort: pd.DataFrame
) -> tuple[dict[float, dict[str, int]], float]:
    """The confusion matrix at each threshold a laboratory director chooses from,
    and AUROC, on this cohort's validation split."""
    net = Net()
    net.load_state_dict(state_dict)
    _, valloader, _ = load_data(cohort)
    _, metrics, probabilities, labels = evaluate(net, valloader)
    deficient = labels == 1
    matrices = {}
    for threshold in THRESHOLDS:
        suggested = probabilities >= threshold
        matrices[threshold] = {
            "true_positives": int((suggested & deficient).sum()),
            "false_negatives": int((~suggested & deficient).sum()),
            "false_positives": int((suggested & ~deficient).sum()),
            "true_negatives": int((~suggested & ~deficient).sum()),
        }
    return matrices, float(metrics["auroc"])


def receive_final_model(
    directory: Path,
    *,
    run_id: int,
    state_dict: dict[str, torch.Tensor],
    cohort: pd.DataFrame,
    federated: dict[str, float],
    stored_at: datetime,
) -> Path:
    """Store a fetched final model; one fetched again is kept as it was.
    Other weights under a stored run's ID are refused (features/final_models.feature)."""
    path = final_model_path(directory, run_id)
    if path.exists():
        stored = read(path).state_dict
        same = (
            stored is not None
            and stored.keys() == state_dict.keys()
            and all(torch.equal(stored[name], state_dict[name]) for name in state_dict)
        )
        if not same:
            raise FileExistsError(f"{path} holds other weights.")
        return path
    return store_final_model(
        directory,
        run_id=run_id,
        state_dict=state_dict,
        cohort=cohort,
        federated=federated,
        stored_at=stored_at,
    )


def store_final_model(
    directory: Path,
    *,
    run_id: int,
    state_dict: dict[str, torch.Tensor],
    cohort: pd.DataFrame,
    federated: dict[str, float],
    stored_at: datetime,
) -> Path:
    """Store a training run's final model with this hospital's standardization.

    `federated` is what the ServerApp aggregated; no other hospital's metrics
    reach this file (features/final_models.feature). A final model is never overwritten (features/final_models.feature).
    """
    path = final_model_path(directory, run_id)
    if path.exists():
        raise FileExistsError(path)
    mean, std = standardization(cohort)
    matrices, local_auroc = local_validation(state_dict, cohort)
    write(
        path,
        FinalModel(
            state_dict=state_dict,
            mean=standardization_tensor(mean),
            std=standardization_tensor(std),
            run_id=run_id,
            stored_at=stored_at,
            federated=federated,
            confusion_matrices=matrices,
            local_auroc=local_auroc,
        ),
    )
    return path
