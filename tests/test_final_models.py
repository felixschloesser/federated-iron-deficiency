"""Final models as each hospital stores them (spec R16, R20)."""

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import torch

from iron_deficiency.dataset import FEATURES
from iron_deficiency.final_models import store_final_model
from iron_deficiency.screening import score
from iron_deficiency.task import Net

STORED_AT = datetime(2026, 10, 30, 9, 0, tzinfo=UTC)
FEDERATED = {"eval_auroc": 0.85, "eval_loss": 0.41}


@pytest.fixture
def cohort() -> pd.DataFrame:
    """A small cohort with both labels, standing in for one hospital's."""
    rng = np.random.default_rng(0)
    frame = pd.DataFrame(rng.normal(size=(200, len(FEATURES))), columns=FEATURES)
    return frame.assign(iron_deficient=rng.integers(0, 2, size=200))


def store(directory: Path, cohort: pd.DataFrame, run_id: int) -> Path:
    torch.manual_seed(run_id)
    return store_final_model(
        directory,
        run_id=run_id,
        state_dict=Net().state_dict(),
        cohort=cohort,
        threshold=0.5,
        federated=FEDERATED,
        stored_at=STORED_AT,
    )


def test_stores_one_file_per_run_with_its_metadata(
    tmp_path: Path, cohort: pd.DataFrame
) -> None:
    path = store(tmp_path, cohort, run_id=11)
    assert path == tmp_path / "11.pt"
    final_model = torch.load(path)
    assert set(final_model) == {
        "state_dict",
        "mean",
        "std",
        "threshold",
        "run_id",
        "stored_at",
        "federated",
        "local_validation",
    }
    assert final_model["run_id"] == 11
    assert final_model["stored_at"] == STORED_AT.isoformat()
    assert final_model["threshold"] == 0.5


def test_never_overwrites_a_final_model(tmp_path: Path, cohort: pd.DataFrame) -> None:
    first = store(tmp_path, cohort, run_id=11)
    before = first.read_bytes()
    store(tmp_path, cohort, run_id=12)
    with pytest.raises(FileExistsError):
        store(tmp_path, cohort, run_id=11)
    assert first.read_bytes() == before
    assert sorted(path.name for path in tmp_path.iterdir()) == ["11.pt", "12.pt"]


def test_local_validation_is_a_confusion_matrix_and_auroc(
    tmp_path: Path, cohort: pd.DataFrame
) -> None:
    validation = torch.load(store(tmp_path, cohort, run_id=11))["local_validation"]
    assert set(validation) == {
        "true_positives",
        "false_negatives",
        "false_positives",
        "true_negatives",
        "auroc",
    }
    counts = [validation[key] for key in sorted(validation) if key != "auroc"]
    # The validation split is 16% of the cohort (task.load_data).
    assert sum(counts) == 32
    assert 0.0 <= validation["auroc"] <= 1.0


def test_holds_only_the_federated_aggregate(
    tmp_path: Path, cohort: pd.DataFrame
) -> None:
    # R20: no other hospital's metrics, only what the ServerApp aggregated.
    assert torch.load(store(tmp_path, cohort, run_id=11))["federated"] == FEDERATED


def test_a_final_model_screens_like_a_deployment(
    tmp_path: Path, cohort: pd.DataFrame
) -> None:
    path = store(tmp_path, cohort, run_id=11)
    samples = (
        cohort[FEATURES]
        .rename(columns={"RIDAGEYR": "age"})
        .assign(sex="Female", age=30)
    )
    probabilities, threshold = score(samples, path)
    assert threshold == 0.5
    assert len(probabilities) == len(samples)
