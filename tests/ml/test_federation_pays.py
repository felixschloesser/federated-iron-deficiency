"""The report's claim, measured: no hospital loses by federating, and the
smallest gains.

Each hospital's test AUROC of the federated model, against the same network
trained on that hospital's cohort alone with the same run configuration,
averaged over five seeds, as one seed's draw moves the smallest hospital's
gain by about ±0.02. The training is the ClientApp's: the cohort loaded
afresh each round (ml.validation.load_data), ml.training.train, seeded as
ml.client_app and ml.server_app seed; the aggregation FedAvg's: weights
averaged by each hospital's training examples.

What it guards: a change to the cohort or the label (ml/, the hospital's lab
records) that takes away the benefit. What it does not: the aggregation, which
production leaves to Flower's FedAvg, nor the run configuration; 1 or 10
rounds, a learning rate of 0.1 or 5 local epochs all still pass, as the small
hospital's gain comes from the others' data.

Measured on the pinned NHANES revision (2026-11-07), seeds 0–4: +0.016,
+0.004 and +0.062; the configured seed 42: +0.011, −0.004 and +0.044."""

import copy
import tomllib
from pathlib import Path

import pandas as pd
import pytest
import torch

from ml.dataset import cohorts as cycle_cohorts
from ml.final_model import Net
from ml.training import dataset_size, train
from ml.validation import evaluate, load_data

pytestmark = pytest.mark.nhanes

CONFIG = tomllib.loads(Path("pyproject.toml").read_text())["tool"]["flwr"]["app"][
    "config"
]
# How much worse than alone a hospital may do on average, and how much better
# the smallest must: an AUROC on a test split of 19–84 iron-deficient women
# resolves differences of a few hundredths at best.
NO_WORSE_BY = 0.01
SMALLEST_GAINS = 0.03
SEEDS = range(5)


def trained(net: Net, cohort: pd.DataFrame, seed: int) -> dict[str, torch.Tensor]:
    """One hospital's round, as the ClientApp trains it: dropout seeded, and the
    cohort loaded afresh, so each round shuffles from the same seed."""
    torch.manual_seed(seed)
    train(
        net,
        load_data(cohort, CONFIG["batch-size"]).train,
        epochs=CONFIG["local-epochs"],
        lr=CONFIG["learning-rate"],
        weight_decay=CONFIG["weight-decay"],
    )
    return net.state_dict()


def federated(cohorts: list[pd.DataFrame], seed: int) -> Net:
    """FedAvg over the hospitals for the configured rounds."""
    torch.manual_seed(seed)
    model = Net()
    examples = [dataset_size(load_data(cohort).train) for cohort in cohorts]
    for _ in range(CONFIG["num-server-rounds"]):
        weights = [trained(copy.deepcopy(model), cohort, seed) for cohort in cohorts]
        model.load_state_dict(
            {
                name: sum(
                    state[name] * count
                    for state, count in zip(weights, examples, strict=True)
                )
                / sum(examples)
                for name in weights[0]
            }
        )
    return model


def alone(cohort: pd.DataFrame, seed: int) -> Net:
    """The same network, configuration and seeds, on one hospital's cohort."""
    torch.manual_seed(seed)
    model = Net()
    for _ in range(CONFIG["num-server-rounds"]):
        trained(model, cohort, seed)
    return model


def test_no_hospital_loses_by_federating_and_the_smallest_gains() -> None:
    cohorts = cycle_cohorts()
    tests = [load_data(cohort).test for cohort in cohorts]
    gains = [0.0] * len(cohorts)
    for seed in SEEDS:
        model = federated(cohorts, seed)
        for at, (cohort, test) in enumerate(zip(cohorts, tests, strict=True)):
            gains[at] += (
                evaluate(model, test).auroc - evaluate(alone(cohort, seed), test).auroc
            ) / len(SEEDS)
    assert min(gains) >= -NO_WORSE_BY, gains
    smallest = min(range(len(tests)), key=lambda at: dataset_size(tests[at]))
    assert gains[smallest] >= SMALLEST_GAINS, gains
