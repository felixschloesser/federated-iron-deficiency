"""ClientApp: each hospital trains and evaluates on its own cohort."""

from pathlib import Path

import pandas as pd
import torch
from flwr.app import (
    ArrayRecord,
    ConfigRecord,
    Context,
    Message,
    MetricRecord,
    RecordDict,
)
from flwr.clientapp import ClientApp
from flwr_datasets import FederatedDataset

from ml import training, validation
from ml.dataset import load_federated_dataset
from ml.final_model import Net
from ml.training_cohort import read_training_cohort

app = ClientApp()

fds: FederatedDataset | None = None  # Cache across calls in a simulation
# Where a run's state notes the training cohort it reads.
TRAINING_COHORT = "training-cohort"


def load_cohort(context: Context) -> pd.DataFrame:
    """Load this node's cohort: at a hospital, the training cohort its laboratory
    director provided, the same one every round of a run
    (features/training_cohort_in_runs.feature)."""
    # Deployment Runtime: the training cohort, noted in the run's state, which
    # Flower keeps on this SuperNode from round to round.
    if "data-path" in context.node_config:
        noted = context.state.config_records.get(TRAINING_COHORT)
        digest, rows = read_training_cohort(
            Path(str(context.node_config["data-path"])),
            None if noted is None else str(noted["sha256"]),
        )
        context.state[TRAINING_COHORT] = ConfigRecord({"sha256": digest})
        return rows

    # Simulation Runtime: download and partition the cohort on the fly
    global fds
    if fds is None:
        fds = load_federated_dataset()
    partition_id = int(context.node_config["partition-id"])
    return fds.load_partition(partition_id).to_pandas()


def config_float(msg: Message, key: str) -> float:
    """Return a float the ServerApp sent in the message's config record."""
    value = msg.content.config_records["config"][key]
    if not isinstance(value, float):
        raise TypeError(f"Config value {key!r} is not a float")
    return value


@app.train()
def train(msg: Message, context: Context) -> Message:
    """Train the global model on this node's cohort's training split. On the CPU:
    a GPU is slower for so small a network, and not deterministic."""
    # Seed dropout so that runs, and the report's demo numbers, are reproducible
    torch.manual_seed(int(context.run_config["model-seed"]))
    model = Net()
    model.load_state_dict(msg.content.array_records["arrays"].to_torch_state_dict())
    batch_size = int(context.run_config["batch-size"])
    trainloader = validation.load_data(load_cohort(context), batch_size).train
    train_loss = training.train(
        model,
        trainloader,
        epochs=int(context.run_config["local-epochs"]),
        lr=config_float(msg, "lr"),
        weight_decay=float(context.run_config["weight-decay"]),
    )
    model_record = ArrayRecord(model.state_dict())
    metric_record = MetricRecord(
        {"train_loss": train_loss, "num-examples": training.dataset_size(trainloader)}
    )
    content = RecordDict({"arrays": model_record, "metrics": metric_record})
    return Message(content=content, reply_to=msg)


@app.evaluate()
def evaluate(msg: Message, context: Context) -> Message:
    """Evaluate the global model on this node's cohort's validation split."""
    model = Net()
    model.load_state_dict(msg.content.array_records["arrays"].to_torch_state_dict())
    batch_size = int(context.run_config["batch-size"])
    valloader = validation.load_data(load_cohort(context), batch_size).validation
    evaluation = validation.evaluate(model, valloader)
    metric_record = MetricRecord(
        {
            "eval_loss": evaluation.loss,
            "eval_auroc": evaluation.auroc,
            "num-examples": training.dataset_size(valloader),
        }
    )
    content = RecordDict({"metrics": metric_record})
    return Message(content=content, reply_to=msg)
