"""Train the federated and centralized models once per seed and evaluate every hospital's deployment."""

import argparse
import dataclasses
import subprocess
from pathlib import Path

import pandas as pd
from scipy import stats

from analysis.evaluate_screening import evaluate
from analysis.train_centralized import train_centralized
from ml.dataset import load_ferritin
from ml.final_models import (
    DEFAULT_DEMO_DIR,
    hospital_screening_models,
    latest_final_model,
)
from ml.screening import COLUMNS, read

HOSPITALS = {0: "UZ Leuven", 1: "Heilig Hart Leuven", 2: "AZ Diest"}
# Largest AUROC difference we would still call equivalent, fixed before running.
MARGIN = 0.01


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=10)
    parser.add_argument("--input", type=Path, default=Path("demo_data/new_samples.csv"))
    parser.add_argument("--output", type=Path, default=Path("seed_sweep.csv"))
    # The report's fixed 0.5: every hospital deploys at one threshold, so the
    # arms differ only in their weights and standardization.
    parser.add_argument("--threshold", type=float, default=0.5)
    args = parser.parse_args()

    samples = pd.read_csv(args.input, usecols=COLUMNS)
    ferritin = load_ferritin()

    rows = []
    for seed in range(args.seeds):
        subprocess.run(
            [
                "flwr",
                "run",
                ".",
                "--federation-config",
                "num-supernodes=3",
                "--run-config",
                f"model-seed={seed}",
                "--stream",
            ],
            check=True,
            capture_output=True,
        )
        centralized = train_centralized(seed)
        for partition_id, hospital in HOSPITALS.items():
            federated = read(
                latest_final_model(
                    hospital_screening_models(DEFAULT_DEMO_DIR, partition_id)
                )
            )
            rows.append(
                {
                    "seed": seed,
                    "arm": "federated",
                    "hospital": hospital,
                    **evaluate(federated, samples, ferritin, args.threshold),
                }
            )
            # Deploy the centralized weights with this hospital's standardization.
            centralized_model = dataclasses.replace(federated, state_dict=centralized)
            rows.append(
                {
                    "seed": seed,
                    "arm": "centralized",
                    "hospital": hospital,
                    **evaluate(centralized_model, samples, ferritin, args.threshold),
                }
            )
        print(f"Seed {seed} done")

    results = pd.DataFrame(rows)
    results.to_csv(args.output, index=False)
    summary = results.groupby(["arm", "hospital"])[
        ["suggested", "suggested_above_cutoff", "suggested_deficient", "auroc"]
    ].agg(["mean", "std", "min", "max"])
    print(summary.round(3).to_string())

    # Same weights in every hospital, so the per-seed difference isolates the deployment.
    federated_rows = results[results["arm"] == "federated"]
    suggested = federated_rows.pivot(
        index="seed", columns="hospital", values="suggested"
    )
    difference = suggested["UZ Leuven"] - suggested["AZ Diest"]
    print(
        f"\nUZ Leuven minus AZ Diest flags (federated): mean {difference.mean():.1f}, "
        f"SD {difference.std():.1f}, positive in {(difference > 0).sum()} of {len(difference)} seeds"
    )

    # Paired by seed: federated minus centralized AUROC at each hospital.
    auroc = results.pivot_table(
        index=["seed", "hospital"], columns="arm", values="auroc"
    )
    for hospital_name, group in (auroc["federated"] - auroc["centralized"]).groupby(
        "hospital"
    ):
        n, mean, sem = len(group), group.mean(), stats.sem(group)
        low95, high95 = stats.t.interval(0.95, n - 1, loc=mean, scale=sem)
        # TOST: equivalent if the 90% interval lies inside ±MARGIN.
        low90, high90 = stats.t.interval(0.90, n - 1, loc=mean, scale=sem)
        verdict = (
            "equivalent"
            if -MARGIN < low90 and high90 < MARGIN
            else "not shown equivalent"
        )
        print(
            f"{hospital_name}: federated minus centralized AUROC {mean:+.4f} "
            f"(95% CI {low95:+.4f} to {high95:+.4f}); {verdict} within ±{MARGIN}"
        )


if __name__ == "__main__":
    main()
