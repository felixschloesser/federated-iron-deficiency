"""Data loading, training and evaluation; then the final model as each hospital
keeps and validates it, transmits it, and the startup stores its own copy: one
file per training run."""

from collections.abc import Mapping, Sized
from datetime import UTC, datetime
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
from ml.dataset import CYCLES, HOSPITALS, hospital_slug
from ml.final_model import (
    THRESHOLDS,
    FinalModel,
    Net,
    final_model_path,
    final_model_paths,
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


def final_model_to_transmit(directory: Path, run_id: int) -> FinalModel:
    """What a transmission sends every hospital of the startup's kept final model:
    its weights, the AUROC across hospitals and its run ID; never its run
    configuration (features/training.feature)."""
    path = final_model_path(directory, run_id)
    kept = read(path) if path.is_file() else FinalModel()
    if kept.state_dict is None:
        raise FileNotFoundError(f"There is no final model of run {run_id}.")
    return FinalModel(
        state_dict=kept.state_dict, run_id=run_id, federated=kept.federated
    )


def transmission_failure(*, connected: int, replied: int, errors: int) -> str | None:
    """Why a transmission did not reach every connected hospital, or None when
    each acknowledged it. Flower leaves a missing reply out, not as an error."""
    if connected == 0:
        return "No hospital is connected."
    if replied < connected:
        return f"{replied} of {connected} connected hospitals replied."
    if errors:
        return f"{errors} of {connected} connected hospitals could not store it."
    return None


def receive_final_model(
    directory: Path,
    *,
    run_id: int,
    state_dict: dict[str, torch.Tensor],
    cohort: pd.DataFrame,
    federated: dict[str, float],
    stored_at: datetime,
) -> Path:
    """Store a transmitted final model; one transmitted again is kept as it was.
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
