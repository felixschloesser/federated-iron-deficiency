"""Evaluate a deployed model against the ferritin the screening never sees."""

import argparse
from pathlib import Path

import datasets
import pandas as pd
from sklearn.metrics import roc_auc_score

from iron_deficiency.dataset import (
    FERRITIN_THRESHOLD,
    HF_COLUMNS,
    HF_DATA_FILE,
    HF_DATASET,
    HF_REVISION,
    NEW_SAMPLES_YEAR,
)
from iron_deficiency.screening import COLUMNS, score


def load_ferritin() -> pd.DataFrame:
    """Return the ferritin results of the new samples, keyed by sample ID."""
    merged = (
        datasets.load_dataset(
            HF_DATASET,
            revision=HF_REVISION,
            data_files=HF_DATA_FILE,
            columns=list(HF_COLUMNS),
            split="train",
        )
        .to_pandas()
        .rename(columns=HF_COLUMNS)
    )
    ferritin = merged.loc[merged["YEAR"] == NEW_SAMPLES_YEAR, ["SEQN", "LBXFER"]]
    return ferritin.rename(columns={"SEQN": "sample_id"})


def evaluate(model: Path, samples: pd.DataFrame, ferritin: pd.DataFrame) -> dict:
    """Return the AUROC and confusion matrix of a deployed model's flags."""
    probabilities, threshold = score(samples, model)
    eligible = samples.loc[probabilities.index].assign(probability=probabilities)
    eligible = eligible.merge(ferritin, on="sample_id", how="left")
    # NHANES measures ferritin only in a subsample; women without it can't be scored.
    tested = eligible.dropna(subset=["LBXFER"])
    deficient = tested["LBXFER"] < FERRITIN_THRESHOLD
    flagged = tested["probability"] >= threshold
    return {
        "eligible": len(eligible),
        "flagged": int((eligible["probability"] >= threshold).sum()),
        "with_ferritin": len(tested),
        "auroc": roc_auc_score(deficient, tested["probability"]),
        "flagged_deficient": int((flagged & deficient).sum()),
        "flagged_above_cutoff": int((flagged & ~deficient).sum()),
        "missed_deficient": int((~flagged & deficient).sum()),
        "not_flagged_above_cutoff": int((~flagged & ~deficient).sum()),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()

    result = evaluate(
        args.model, pd.read_csv(args.input, usecols=COLUMNS), load_ferritin()
    )
    print(f"Eligible: {result['eligible']}, with ferritin: {result['with_ferritin']}")
    print(f"Flagged: {result['flagged']}")
    print(f"AUROC: {result['auroc']:.3f}\n")
    print("              deficient  ferritin >= cutoff")
    print(f"flagged       {result['flagged_deficient']:>9}  {result['flagged_above_cutoff']:>18}")
    print(f"not flagged   {result['missed_deficient']:>9}  {result['not_flagged_above_cutoff']:>18}")
