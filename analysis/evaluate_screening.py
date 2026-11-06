"""Evaluate a deployed model against the ferritin the screening never sees."""

import argparse
from pathlib import Path

import pandas as pd
from sklearn.metrics import roc_auc_score

from ml.cohort import FERRITIN_CUTOFF
from ml.dataset import load_ferritin
from ml.screening import COLUMNS, FinalModel, read, score


def evaluate(
    model: FinalModel, samples: pd.DataFrame, ferritin: pd.DataFrame, threshold: float
) -> dict[str, float]:
    """Return the AUROC and confusion matrix of a model's flags, deployed at the
    threshold."""
    probabilities = score(samples, model)
    eligible = samples.loc[probabilities.index].assign(probability=probabilities)
    eligible = eligible.merge(ferritin, on="sample_id", how="left")
    # NHANES measures ferritin only in a subsample; women without it can't be scored.
    tested = eligible.dropna(subset=["LBXFER"])
    deficient = tested["LBXFER"] < FERRITIN_CUTOFF
    suggested = tested["probability"] >= threshold
    return {
        "eligible": len(eligible),
        "suggested": int((eligible["probability"] >= threshold).sum()),
        "with_ferritin": len(tested),
        "auroc": roc_auc_score(deficient, tested["probability"]),
        "suggested_deficient": int((suggested & deficient).sum()),
        "suggested_above_cutoff": int((suggested & ~deficient).sum()),
        "missed_deficient": int((~suggested & deficient).sum()),
        "not_suggested_above_cutoff": int((~suggested & ~deficient).sum()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument(
        "--threshold", type=float, required=True, help="the deployed threshold"
    )
    args = parser.parse_args()

    result = evaluate(
        read(args.model),
        pd.read_csv(args.input, usecols=COLUMNS),
        load_ferritin(),
        args.threshold,
    )
    print(f"Eligible: {result['eligible']}, with ferritin: {result['with_ferritin']}")
    print(f"Ferritin suggested: {result['suggested']}")
    print(f"AUROC: {result['auroc']:.3f}\n")
    print("              deficient  ferritin >= cutoff")
    print(
        f"suggested     {result['suggested_deficient']:>9}  {result['suggested_above_cutoff']:>18}"
    )
    print(
        f"not suggested {result['missed_deficient']:>9}  {result['not_suggested_above_cutoff']:>18}"
    )


if __name__ == "__main__":
    main()
