"""Inference: a screening model's probability for one CBC (ml/inference.py)."""

import pandas as pd
import pytest

from ml.cohort import CBC_VARS, FEATURES
from ml.final_model import Net, standardization_tensor
from ml.inference import probability

ZEROS = pd.Series(0.0, index=FEATURES)
MEAN, STD = standardization_tensor(ZEROS), standardization_tensor(ZEROS + 1)


def test_a_complete_cbc_gets_a_probability() -> None:
    cbc = dict.fromkeys(CBC_VARS, 1.0)
    assert 0.0 <= probability(Net().state_dict(), MEAN, STD, cbc, age=30) <= 1.0


def test_a_cbc_missing_a_value_is_refused() -> None:
    cbc = dict.fromkeys(CBC_VARS[1:], 1.0)
    with pytest.raises(ValueError, match="without all its values"):
        probability(Net().state_dict(), MEAN, STD, cbc, age=30)
