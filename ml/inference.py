"""Inference: a final model's probability of iron deficiency for one CBC. The
hospital decides what to make of it (hospital/deployment/models.py, Screener)."""

from collections.abc import Mapping

import pandas as pd
import torch

from ml.cohort import FEATURES
from ml.final_model import Net


def probability(
    state_dict: dict[str, torch.Tensor],
    mean: torch.Tensor,
    std: torch.Tensor,
    cbc: Mapping[str, float],
    age: int,
) -> float:
    """The probability of iron deficiency the weights give one CBC and age, from
    unstandardized values standardized by `mean` and `std`; who is screened is
    the caller's decision."""
    values = pd.DataFrame([{**cbc, "RIDAGEYR": age}], columns=FEATURES)
    if values.isna().any(axis=None):
        raise ValueError("A CBC without all its values cannot be screened.")
    net = Net()
    net.load_state_dict(state_dict)
    net.eval()
    features = torch.tensor(values.values, dtype=torch.float32)
    with torch.no_grad():
        return float(torch.sigmoid(net((features - mean) / std))[0])
