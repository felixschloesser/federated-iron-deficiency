"""Local screening of new blood counts with the deployed model."""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from iron_deficiency.dataset import CBC_VARS, FEATURES
from iron_deficiency.task import Net

# One lab export row: sample ID, registered sex, age, and the 13 CBC values.
COLUMNS = ["sample_id", "sex", "age", *CBC_VARS]

# The model was trained on women aged 18–49 only; nobody else gets a result.
ELIGIBLE_SEX = "Female"
ELIGIBLE_AGES = (18, 49)


def save_deployment(
    path: Path,
    state_dict: dict[str, torch.Tensor],
    mean: pd.Series,
    std: pd.Series,
    threshold: float,
) -> None:
    """Store the model with this hospital's standardization and the threshold."""
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "state_dict": state_dict,
            "mean": torch.tensor(mean[FEATURES].values, dtype=torch.float32),
            "std": torch.tensor(std[FEATURES].values, dtype=torch.float32),
            "threshold": threshold,
        },
        path,
    )


def score(samples: pd.DataFrame, model_path: Path) -> tuple[pd.Series, float]:
    """Return the eligible samples' probabilities of iron deficiency, and the threshold."""
    deployment = torch.load(model_path)
    net = Net()
    net.load_state_dict(deployment["state_dict"])
    net.eval()

    features = samples[CBC_VARS].assign(RIDAGEYR=samples["age"])[FEATURES]
    eligible = (
        (samples["sex"] == ELIGIBLE_SEX)
        & samples["age"].between(*ELIGIBLE_AGES)
        & features.notna().all(axis=1)
    )
    x = torch.tensor(features[eligible].values, dtype=torch.float32)
    x = (x - deployment["mean"]) / deployment["std"]
    with torch.no_grad():
        probabilities = torch.sigmoid(net(x)).numpy()
    return pd.Series(probabilities, index=samples.index[eligible]), deployment["threshold"]


def screen(samples: pd.DataFrame, model_path: Path) -> pd.DataFrame:
    """Return each sample's ID and result: flagged, not flagged, or not screened."""
    probabilities, threshold = score(samples, model_path)
    result = pd.Series("not screened", index=samples.index)
    result[probabilities.index] = np.where(
        probabilities >= threshold, "flagged", "not flagged"
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
    args = parser.parse_args()

    results = screen(pd.read_csv(args.input, usecols=COLUMNS), args.model)
    results.to_csv(args.output, index=False)
    # Print counts only, so no sample ID ends up in the terminal or its logs.
    print(results["result"].value_counts().to_string())
