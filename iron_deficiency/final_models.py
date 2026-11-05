"""Final models as each hospital stores them: one file per training run."""

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import torch

from iron_deficiency.dataset import CYCLES, HOSPITALS, hospital_slug
from iron_deficiency.screening import (
    FinalModel,
    final_model_path,
    read,
    standardization_tensor,
    write,
)
from iron_deficiency.task import Net, load_data, standardization, test

# Where final models live when no demo directory is configured.
DEFAULT_DEMO_DIR = Path.home() / ".cache" / "iron-deficiency"


def hospital_final_models(demo_dir: Path, partition_id: int) -> Path:
    """The screening-models folder of the hospital that holds this partition."""
    cycle = list(CYCLES)[partition_id]  # Partition IDs follow CYCLES order
    return demo_dir / "hospitals" / hospital_slug(HOSPITALS[cycle]) / "screening-models"


def startup_final_models(demo_dir: Path) -> Path:
    """The startup's own copy of every final model (report DS4)."""
    return demo_dir / "startup" / "final-models"


def latest_final_model(directory: Path) -> Path:
    """The final model stored last in a folder."""
    unknown = datetime.min.replace(tzinfo=UTC)
    return max(directory.glob("*.pt"), key=lambda path: read(path).stored_at or unknown)


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
    reach this file (features/final_models.feature). A final model is never overwritten (features/final_models.feature).
    """
    path = final_model_path(directory, run_id)
    if path.exists():
        raise FileExistsError(path)
    mean, std = standardization(cohort)
    write(
        path,
        FinalModel(
            state_dict=state_dict,
            mean=standardization_tensor(mean),
            std=standardization_tensor(std),
            threshold=threshold,
            run_id=run_id,
            stored_at=stored_at,
            federated=federated,
            local_validation=local_validation(state_dict, cohort, threshold),
        ),
    )
    return path
