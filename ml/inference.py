"""Inference: the deployed model on new blood counts, at the hospital. The
hospital calls it screening; screen() and suggests_ferritin() speak its words."""

import argparse
from collections.abc import Mapping
from pathlib import Path

import numpy as np
import numpy.typing as npt
import pandas as pd
import torch

from ml.cohort import CBC_VARS, FEATURES, eligible
from ml.final_model import FinalModel, Net, read

# One lab export row: sample ID, registered sex, age, and the 13 CBC values.
COLUMNS = ["sample_id", "sex", "age", *CBC_VARS]


def probabilities_of(
    model: FinalModel, features: pd.DataFrame
) -> npt.NDArray[np.float32]:
    """Each row's probability of iron deficiency, from unstandardized FEATURES."""
    if model.state_dict is None or model.mean is None or model.std is None:
        raise ValueError(f"This final model cannot screen: {model.problem()}")
    net = Net()
    net.load_state_dict(model.state_dict)
    net.eval()
    x = torch.tensor(features[FEATURES].values, dtype=torch.float32)
    with torch.no_grad():
        probabilities: npt.NDArray[np.float32] = torch.sigmoid(
            net((x - model.mean) / model.std)
        ).numpy()
    return probabilities


def score(samples: pd.DataFrame, model: FinalModel) -> pd.Series:
    """Return the eligible samples' probabilities of iron deficiency."""
    features = samples[CBC_VARS].assign(RIDAGEYR=samples["age"])[FEATURES]
    scored = eligible(samples["sex"], samples["age"]) & features.notna().all(axis=1)
    probabilities = probabilities_of(model, features[scored])
    return pd.Series(probabilities, index=samples.index[scored])


def suggests_ferritin(
    cbc: Mapping[str, float], age: int, model: FinalModel, threshold: float
) -> bool:
    """Whether the model scores one CBC at or above the threshold it was deployed
    at. Who is screened is the caller's decision (features/hospital/screening.feature)."""
    features = pd.DataFrame([{**cbc, "RIDAGEYR": age}], columns=FEATURES)
    if features.isna().any(axis=None):
        raise ValueError("A CBC without all its values cannot be screened.")
    return bool(probabilities_of(model, features)[0] >= threshold)


def screen(samples: pd.DataFrame, model: FinalModel, threshold: float) -> pd.DataFrame:
    """Return each sample's screening result: ferritin suggested, ferritin not
    suggested, or not screened."""
    probabilities = score(samples, model)
    result = pd.Series("not screened", index=samples.index)
    result[probabilities.index] = np.where(
        probabilities >= threshold, "ferritin suggested", "ferritin not suggested"
    )

    # Only the sample ID and the decision leave: no score, no other input column.
    return pd.DataFrame({"sample_id": samples["sample_id"], "result": result})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Screen a lab export of new blood counts with the deployed model."
    )
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--threshold", type=float, required=True, help="the deployed threshold"
    )
    args = parser.parse_args()

    results = screen(
        pd.read_csv(args.input, usecols=COLUMNS), read(args.model), args.threshold
    )
    results.to_csv(args.output, index=False)
    # Print counts only, so no sample ID ends up in the terminal or its logs.
    print(results["result"].value_counts().to_string())
