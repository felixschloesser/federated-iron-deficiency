"""Evaluate a deployed model against the ferritin the screening never sees."""

import argparse
from pathlib import Path

import pandas as pd
from sklearn.metrics import roc_auc_score

from iron_deficiency.cohort import FERRITIN_THRESHOLD
from iron_deficiency.dataset import load_ferritin
from iron_deficiency.screening import COLUMNS, FinalModel, read, score


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
    print(f"Flagged: {result['flagged']}")
    print(f"AUROC: {result['auroc']:.3f}\n")
    print("              deficient  ferritin >= cutoff")
    print(
        f"flagged       {result['flagged_deficient']:>9}  {result['flagged_above_cutoff']:>18}"
    )
    print(
        f"not flagged   {result['missed_deficient']:>9}  {result['not_flagged_above_cutoff']:>18}"
    )


if __name__ == "__main__":
    main()
