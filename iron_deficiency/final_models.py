"""Final models as each hospital stores them: one file per training run."""

from datetime import datetime
from pathlib import Path

import pandas as pd
import torch

from iron_deficiency.dataset import CYCLES, FEATURES, HOSPITALS
from iron_deficiency.task import Net, load_data, standardization, test

# Where final models live when no demo directory is configured.
DEFAULT_DEMO_DIR = Path.home() / ".cache" / "iron-deficiency"


def hospital_final_models(demo_dir: Path, partition_id: int) -> Path:
    """The final-models folder of the hospital that holds this partition."""
    cycle = list(CYCLES)[partition_id]  # Partition IDs follow CYCLES order
    return demo_dir / "hospitals" / HOSPITALS[cycle] / "final-models"


def startup_final_models(demo_dir: Path) -> Path:
    """The startup's own copy of every final model (report DS4)."""
    return demo_dir / "startup" / "final-models"


def latest_final_model(directory: Path) -> Path:
    """The final model stored last in a folder."""
    return max(directory.glob("*.pt"), key=lambda path: torch.load(path)["stored_at"])


def local_validation(
    state_dict: dict[str, torch.Tensor], cohort: pd.DataFrame, threshold: float
) -> dict[str, float]:
    """The confusion matrix at the threshold, and AUROC, on this cohort's validation split."""
    net = Net()
    net.load_state_dict(state_dict)
    _, valloader, _ = load_data(cohort)
    _, metrics, probabilities, labels = test(net, valloader)
    suggested = probabilities >= threshold
    deficient = labels == 1
    return {
        "true_positives": int((suggested & deficient).sum()),
        "false_negatives": int((~suggested & deficient).sum()),
        "false_positives": int((suggested & ~deficient).sum()),
        "true_negatives": int((~suggested & ~deficient).sum()),
        "auroc": metrics["auroc"],
    }


def store_final_model(
    directory: Path,
    *,
    run_id: int,
    state_dict: dict[str, torch.Tensor],
    cohort: pd.DataFrame,
    threshold: float,
    federated: dict[str, float],
    stored_at: datetime,
) -> Path:
    """Store a training run's final model with this hospital's standardization.

    `federated` is what the ServerApp aggregated; no other hospital's metrics
    reach this file (spec R20). A final model is never overwritten (R16).
    """
    path = directory / f"{run_id}.pt"
    if path.exists():
        raise FileExistsError(path)
    mean, std = standardization(cohort)
    directory.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "state_dict": state_dict,
            "mean": torch.tensor(mean[FEATURES].values, dtype=torch.float32),
            "std": torch.tensor(std[FEATURES].values, dtype=torch.float32),
            "threshold": threshold,
            "run_id": run_id,
            "stored_at": stored_at.isoformat(),
            "federated": federated,
            "local_validation": local_validation(state_dict, cohort, threshold),
        },
        path,
    )
    return path
