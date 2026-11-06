"""Final models as each hospital stores them, and the startup's own copy: one
file per training run."""

from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import torch

from iron_deficiency.dataset import CYCLES, HOSPITALS, hospital_slug
from iron_deficiency.screening import (
    THRESHOLDS,
    FinalModel,
    final_model_path,
    final_model_paths,
    read,
    standardization_tensor,
    write,
)
from iron_deficiency.task import Net, load_data, standardization, test

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


def hospital_final_models(demo_dir: Path, partition_id: int) -> Path:
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
    _, metrics, probabilities, labels = test(net, valloader)
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
