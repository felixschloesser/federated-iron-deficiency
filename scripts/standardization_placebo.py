"""Score one fixed model under different standardizations to see what moves the flags."""

import argparse
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from evaluate_screening import evaluate, load_ferritin
from iron_deficiency.dataset import load_federated_dataset
from iron_deficiency.screening import COLUMNS, save_deployment
from iron_deficiency.task import standardization

HOSPITALS = {0: "UZ Leuven", 1: "Heilig Hart Leuven", 2: "AZ Diest"}

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument(
    "--model",
    type=Path,
    default=Path.home() / ".cache" / "iron-deficiency" / "partition-2" / "model.pt",
)
parser.add_argument("--input", type=Path, default=Path("demo_data/new_samples.csv"))
parser.add_argument("--resamples", type=int, default=200)
args = parser.parse_args()

deployment = torch.load(args.model, weights_only=False)
samples = pd.read_csv(args.input, usecols=COLUMNS)
ferritin = load_ferritin()
fds = load_federated_dataset()
cohorts = {name: fds.load_partition(i).to_pandas() for i, name in HOSPITALS.items()}
rng = np.random.default_rng(0)


def flags_with(cohort: pd.DataFrame) -> dict:
    """Evaluate the fixed weights with the standardization of `cohort`'s training split."""
    mean, std = standardization(cohort)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "model.pt"
        save_deployment(path, deployment["state_dict"], mean, std, deployment["threshold"])
        return evaluate(path, samples, ferritin)


def spread(results: list[dict]) -> str:
    flagged = np.array([r["flagged"] for r in results])
    low, mid, high = np.percentile(flagged, [2.5, 50, 97.5])
    return f"median {mid:.0f}, 95% range {low:.0f}–{high:.0f}"


for name, cohort in cohorts.items():
    result = flags_with(cohort)
    print(f"{name} statistics: {result['flagged']} flagged, AUROC {result['auroc']:.3f}")
result = flags_with(pd.concat(cohorts.values()))
print(f"Pooled statistics: {result['flagged']} flagged, AUROC {result['auroc']:.3f}")

seeds = rng.integers(2**31, size=(2, args.resamples))
az_diest = cohorts["AZ Diest"]
bootstrap = [flags_with(az_diest.sample(frac=1, replace=True, random_state=s)) for s in seeds[0]]
print(f"AZ Diest bootstrap: {spread(bootstrap)}")
# Same size as AZ Diest's cohort, so the spread shows sampling noise at that size.
subsamples = [
    flags_with(cohorts["UZ Leuven"].sample(n=len(az_diest), random_state=s)) for s in seeds[1]
]
print(f"UZ Leuven, {len(az_diest)}-row subsamples: {spread(subsamples)}")
