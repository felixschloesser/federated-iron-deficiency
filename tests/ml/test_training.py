"""No training step averages fewer records than the batch size
(ml/validation.py, ml/training.py)."""

import pandas as pd
import pytest

from ml.cohort import FEATURES
from ml.final_model import Net
from ml.training import train
from ml.validation import load_data


def cohort(rows: int) -> pd.DataFrame:
    return pd.DataFrame(
        {var: [float(row) for row in range(rows)] for var in FEATURES}
        | {"iron_deficient": [row % 2 for row in range(rows)]}
    )


def test_every_training_batch_is_full() -> None:
    # 100 rows give a training split of 64; batches of 32 leave nothing over,
    # batches of 48 leave 16, which are dropped.
    for batch_size in (32, 48):
        trainloader = load_data(cohort(100), batch_size).train
        assert [len(labels) for _, labels in trainloader] == [batch_size] * (
            64 // batch_size
        )


def test_a_split_smaller_than_one_batch_is_refused() -> None:
    trainloader = load_data(cohort(100), 128).train
    with pytest.raises(ValueError, match="fewer than one batch of 128"):
        train(Net(), trainloader)
