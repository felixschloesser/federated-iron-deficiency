"""Inference: a final model's probability of iron deficiency for one CBC. The
hospital decides what to make of it (hospital/deployment/models.py, Screener)."""

from collections.abc import Mapping

import pandas as pd
import torch

from ml.cohort import FEATURES
from ml.final_model import FinalModel, Net


def probability(model: FinalModel, cbc: Mapping[str, float], age: int) -> float:
    """The probability of iron deficiency the model gives one CBC and age, from
    unstandardized values; who is screened is the caller's decision."""
    if model.state_dict is None or model.mean is None or model.std is None:
        raise ValueError(f"This final model cannot screen: {model.problem()}")
    values = pd.DataFrame([{**cbc, "RIDAGEYR": age}], columns=FEATURES)
    if values.isna().any(axis=None):
        raise ValueError("A CBC without all its values cannot be screened.")
    net = Net()
    net.load_state_dict(model.state_dict)
    net.eval()
    features = torch.tensor(values.values, dtype=torch.float32)
    with torch.no_grad():
        return float(torch.sigmoid(net((features - model.mean) / model.std))[0])
