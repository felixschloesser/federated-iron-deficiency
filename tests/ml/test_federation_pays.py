"""The report's claim, measured: no hospital loses by federating, and the
smallest gains.

Each hospital's test AUROC of the federated model, against the same network
trained on that hospital's cohort alone with the same run configuration,
averaged over five seeds: one seed is luck (the configured 42 gives the
smallest hospital +0.013, seeds 0–9 +0.034 to +0.068). The training is the
ClientApp's (ml.validation.load_data, ml.training.train, seeded as
ml.client_app and ml.server_app seed), the aggregation FedAvg's: weights
averaged by each hospital's training examples.

What it guards: a change to the cohort or the label (ml/, the hospital's lab
records) that takes away the benefit. What it does not: the aggregation, which
production leaves to Flower's FedAvg, nor the run configuration; 1 or 10
rounds, a learning rate of 0.1 or 5 local epochs all still pass, as the small
hospital's gain comes from the others' data.

Measured on the pinned NHANES revision (2026-11-07), seeds 0–4: +0.009,
+0.008 and +0.049. The federated model matched the best single hospital's
model at each hospital (within 0.003–0.014) but did not beat it."""

import copy
import tomllib
from pathlib import Path

import pytest
import torch

from ml.dataset import CYCLES, load_federated_dataset
from ml.final_model import Net
from ml.training import dataset_size, train
from ml.validation import Loader, Splits, evaluate, load_data

pytestmark = pytest.mark.nhanes

CONFIG = tomllib.loads(Path("pyproject.toml").read_text())["tool"]["flwr"]["app"][
    "config"
]
# How much worse than alone a hospital may do on average, and how much better
# the smallest must: one seed's noise on a test split of 9–45 iron-deficient
# women is about 0.01.
NO_WORSE_BY = 0.01
SMALLEST_GAINS = 0.03
SEEDS = range(5)


def trained(net: Net, loader: Loader, seed: int) -> dict[str, torch.Tensor]:
    """One hospital's round, as the ClientApp trains: dropout seeded each round."""
    torch.manual_seed(seed)
    train(
        net,
        loader,
        epochs=CONFIG["local-epochs"],
        lr=CONFIG["learning-rate"],
        weight_decay=CONFIG["weight-decay"],
    )
    return net.state_dict()


def federated(hospitals: list[Splits[Loader]], seed: int) -> Net:
    """FedAvg over the hospitals for the configured rounds."""
    torch.manual_seed(seed)
    model = Net()
    examples = [dataset_size(hospital.train) for hospital in hospitals]
    for _ in range(CONFIG["num-server-rounds"]):
        weights = [
            trained(copy.deepcopy(model), hospital.train, seed)
            for hospital in hospitals
        ]
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


def alone(hospital: Splits[Loader], seed: int) -> Net:
    """The same network, configuration and seeds, on one hospital's cohort."""
    torch.manual_seed(seed)
    model = Net()
    for _ in range(CONFIG["num-server-rounds"]):
        trained(model, hospital.train, seed)
    return model


def test_no_hospital_loses_by_federating_and_the_smallest_gains() -> None:
    fds = load_federated_dataset()
    hospitals = [
        load_data(fds.load_partition(partition).to_pandas(), CONFIG["batch-size"])
        for partition in range(len(CYCLES))
    ]
    gains = [0.0] * len(hospitals)
    for seed in SEEDS:
        model = federated(hospitals, seed)
        for at, hospital in enumerate(hospitals):
            gains[at] += (
                evaluate(model, hospital.test).auroc
                - evaluate(alone(hospital, seed), hospital.test).auroc
            ) / len(SEEDS)
    assert min(gains) >= -NO_WORSE_BY, gains
    smallest = min(
        range(len(hospitals)), key=lambda at: dataset_size(hospitals[at].test)
    )
    assert gains[smallest] >= SMALLEST_GAINS, gains
