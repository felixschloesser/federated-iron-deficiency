"""Inference: a final model's probability for one CBC (ml/inference.py)."""

import pandas as pd
import pytest

from ml.cohort import CBC_VARS, FEATURES
from ml.final_model import FinalModel, Net, standardization_tensor
from ml.inference import probability


def final_model() -> FinalModel:
    zeros = pd.Series(0.0, index=FEATURES)
    return FinalModel(
        state_dict=Net().state_dict(),
        mean=standardization_tensor(zeros),
        std=standardization_tensor(zeros + 1),
    )


def test_a_complete_cbc_gets_a_probability() -> None:
    cbc = dict.fromkeys(CBC_VARS, 1.0)
    assert 0.0 <= probability(final_model(), cbc, age=30) <= 1.0


def test_a_cbc_missing_a_value_is_refused() -> None:
    cbc = dict.fromkeys(CBC_VARS[1:], 1.0)
    with pytest.raises(ValueError, match="without all its values"):
        probability(final_model(), cbc, age=30)


def test_a_model_without_standardization_is_refused() -> None:
    with pytest.raises(ValueError, match="cannot screen"):
        probability(FinalModel(state_dict=Net().state_dict()), {}, age=30)
