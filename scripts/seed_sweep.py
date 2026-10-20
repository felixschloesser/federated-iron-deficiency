"""Train the federated and centralized models once per seed and evaluate every hospital's deployment."""

import argparse
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import torch
from scipy import stats

from evaluate_screening import evaluate, load_ferritin
from train_centralized import train_centralized
from iron_deficiency.screening import COLUMNS

HOSPITALS = {0: "UZ Leuven", 1: "Heilig Hart Leuven", 2: "AZ Diest"}
# Largest AUROC difference we would still call equivalent, fixed before running.
MARGIN = 0.01

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--seeds", type=int, default=10)
parser.add_argument("--input", type=Path, default=Path("demo_data/new_samples.csv"))
parser.add_argument("--output", type=Path, default=Path("seed_sweep.csv"))
args = parser.parse_args()

samples = pd.read_csv(args.input, usecols=COLUMNS)
ferritin = load_ferritin()
cache = Path.home() / ".cache" / "iron-deficiency"

rows = []
for seed in range(args.seeds):
    subprocess.run(
        [
            "flwr", "run", ".",
            "--federation-config", "num-supernodes=3",
            "--run-config", f"model-seed={seed}",
            "--stream",
        ],
        check=True,
        capture_output=True,
    )
    centralized = train_centralized(seed)
    for partition_id, hospital in HOSPITALS.items():
        federated = cache / f"partition-{partition_id}" / "model.pt"
        rows.append({"seed": seed, "arm": "federated", "hospital": hospital,
                     **evaluate(federated, samples, ferritin)})
        # Deploy the centralized weights with this hospital's standardization and threshold.
        deployment = torch.load(federated, weights_only=False)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "model.pt"
            torch.save({**deployment, "state_dict": centralized}, path)
            rows.append({"seed": seed, "arm": "centralized", "hospital": hospital,
                         **evaluate(path, samples, ferritin)})
    print(f"Seed {seed} done")

results = pd.DataFrame(rows)
results.to_csv(args.output, index=False)
summary = results.groupby(["arm", "hospital"])[
    ["flagged", "flagged_above_cutoff", "flagged_deficient", "auroc"]
].agg(["mean", "std", "min", "max"])
print(summary.round(3).to_string())

# Same weights in every hospital, so the per-seed difference isolates the deployment.
federated = results[results["arm"] == "federated"]
flagged = federated.pivot(index="seed", columns="hospital", values="flagged")
difference = flagged["UZ Leuven"] - flagged["AZ Diest"]
print(
    f"\nUZ Leuven minus AZ Diest flags (federated): mean {difference.mean():.1f}, "
    f"SD {difference.std():.1f}, positive in {(difference > 0).sum()} of {len(difference)} seeds"
)

# Paired by seed: federated minus centralized AUROC at each hospital.
auroc = results.pivot_table(index=["seed", "hospital"], columns="arm", values="auroc")
for hospital, group in (auroc["federated"] - auroc["centralized"]).groupby("hospital"):
    n, mean, sem = len(group), group.mean(), stats.sem(group)
    low95, high95 = stats.t.interval(0.95, n - 1, loc=mean, scale=sem)
    # TOST: equivalent if the 90% interval lies inside ±MARGIN.
    low90, high90 = stats.t.interval(0.90, n - 1, loc=mean, scale=sem)
    verdict = "equivalent" if -MARGIN < low90 and high90 < MARGIN else "not shown equivalent"
    print(
        f"{hospital}: federated minus centralized AUROC {mean:+.4f} "
        f"(95% CI {low95:+.4f} to {high95:+.4f}); {verdict} within ±{MARGIN}"
    )
