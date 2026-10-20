"""ClientApp for federated iron-deficiency classification."""

from pathlib import Path

import pandas as pd
import torch
from datasets import load_from_disk
from flwr.app import ArrayRecord, Context, Message, MetricRecord, RecordDict
from flwr.clientapp import ClientApp

from iron_deficiency.dataset import load_federated_dataset
from iron_deficiency.screening import save_deployment
from iron_deficiency.task import Net, load_data, standardization
from iron_deficiency.task import test as test_fn
from iron_deficiency.task import train as train_fn

# Flower ClientApp
app = ClientApp()

fds = None  # Cache FederatedDataset across calls in a simulation


def load_cohort(context: Context) -> pd.DataFrame:
    """Load this node's NHANES cycle cohort."""
    # Deployment Runtime: read the partition saved on this SuperNode
    if "data-path" in context.node_config:
        return load_from_disk(str(context.node_config["data-path"])).to_pandas()

    # Simulation Runtime: download and partition by cycle on the fly
    global fds
    if fds is None:
        fds = load_federated_dataset()
    partition_id = int(context.node_config["partition-id"])
    return fds.load_partition(partition_id).to_pandas()


@app.train()
def train(msg: Message, context: Context):
    """Train the model on local data."""

    # Seed dropout so that runs, and the report's demo numbers, are reproducible
    torch.manual_seed(context.run_config["model-seed"])

    # Load the model and initialize it with the received weights
    model = Net()
    model.load_state_dict(msg.content["arrays"].to_torch_state_dict())
    device = torch.device(
        "cuda"
        if torch.cuda.is_available()
        else "mps"
        if torch.backends.mps.is_available()
        else "cpu"
    )
    model.to(device)

    # Load the data
    batch_size = context.run_config["batch-size"]
    trainloader, _, _ = load_data(load_cohort(context), batch_size)

    # Call the training function
    train_loss = train_fn(
        model,
        trainloader,
        epochs=context.run_config["local-epochs"],
        lr=msg.content["config"]["lr"],
        weight_decay=context.run_config["weight-decay"],
        device=device,
    )

    # Construct and return reply Message
    model_record = ArrayRecord(model.state_dict())
    metrics = {
        "train_loss": train_loss,
        "num-examples": len(trainloader.dataset),
    }
    metric_record = MetricRecord(metrics)
    content = RecordDict({"arrays": model_record, "metrics": metric_record})
    return Message(content=content, reply_to=msg)


@app.evaluate()
def evaluate(msg: Message, context: Context):
    """Evaluate the model on local validation data."""

    # Load the model and initialize it with the received weights
    model = Net()
    model.load_state_dict(msg.content["arrays"].to_torch_state_dict())
    device = torch.device(
        "cuda"
        if torch.cuda.is_available()
        else "mps"
        if torch.backends.mps.is_available()
        else "cpu"
    )
    model.to(device)

    # Load the data
    batch_size = context.run_config["batch-size"]
    _, valloader, _ = load_data(load_cohort(context), batch_size)

    # Call the evaluation function
    eval_loss, eval_metrics, _, _ = test_fn(
        model,
        valloader,
        device=device,
    )

    # Construct and return reply Message
    metrics = {
        "eval_loss": eval_loss,
        "eval_auroc": eval_metrics["auroc"],
        "num-examples": len(valloader.dataset),
    }
    metric_record = MetricRecord(metrics)
    content = RecordDict({"metrics": metric_record})
    return Message(content=content, reply_to=msg)


def model_path(context: Context) -> Path:
    """Return where this node keeps its deployed model."""
    # Deployment Runtime: the hospital chooses where the model is stored
    if "data-path" in context.node_config:
        return Path(str(context.node_config["model-path"]))

    # Simulation Runtime: one folder per virtual SuperNode in the user's cache
    partition_id = int(context.node_config["partition-id"])
    cache = Path.home() / ".cache" / "iron-deficiency"
    return cache / f"partition-{partition_id}" / "model.pt"


@app.query("deploy")
def deploy(msg: Message, context: Context):
    """Store the final model with this hospital's standardization for screening."""

    mean, std = standardization(load_cohort(context))
    save_deployment(
        model_path(context),
        msg.content["arrays"].to_torch_state_dict(),
        mean,
        std,
        float(msg.content["config"]["threshold"]),
    )
    return Message(content=RecordDict(), reply_to=msg)
