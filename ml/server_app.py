"""ServerApp for federated iron-deficiency classification."""

from datetime import UTC, datetime
from pathlib import Path

import torch
from flwr.app import (
    ArrayRecord,
    ConfigRecord,
    Context,
    Message,
    MetricRecord,
    RecordDict,
)
from flwr.serverapp import Grid, ServerApp
from flwr.serverapp.strategy import FedAvg, Result

from ml.final_models import (
    DEFAULT_DEMO_DIR,
    final_model_to_transmit,
    keep_final_model,
    startup_final_models,
    training_parameters,
    transmission_failure,
)
from ml.task import Net

# Create ServerApp
app = ServerApp()


def _log_result_to_wandb(result: Result, api_key: str) -> None:
    """Log the metrics collected by the strategy to Weights & Biases."""
    import wandb

    metric_groups = {
        "train": result.train_metrics_clientapp,
        "evaluate": result.evaluate_metrics_clientapp,
        "server_evaluate": result.evaluate_metrics_serverapp,
    }
    rounds = sorted(
        {round_number for group in metric_groups.values() for round_number in group}
    )

    wandb.login(key=api_key)
    with wandb.init(project="iron-deficiency") as run:
        run.define_metric("*", step_metric="round")
        for round_number in rounds:
            metrics: dict[str, int | float | list[int] | list[float]] = {
                "round": round_number
            }
            for group_name, group in metric_groups.items():
                if metric_record := group.get(round_number):
                    metrics.update(
                        {
                            f"{group_name}/{metric_name}": metric_value
                            for metric_name, metric_value in metric_record.items()
                        }
                    )
            run.log(metrics)


@app.main()
def main(grid: Grid, context: Context) -> None:
    """A training run, or, with `transmit-final-model` set, the transmission of a
    final model the startup kept to every hospital (features/training.feature)."""
    demo_dir = Path(str(context.run_config["demo-dir"]) or DEFAULT_DEMO_DIR)
    # A string: Flower's run IDs exceed TOML's integers; empty for a training run.
    transmit = str(context.run_config["transmit-final-model"])
    if transmit:
        transmit_final_model(grid, startup_final_models(demo_dir), int(transmit))
    else:
        train(grid, context, startup_final_models(demo_dir))


def transmit_final_model(grid: Grid, directory: Path, run_id: int) -> None:
    """Send the startup's kept final model to every connected hospital, and fail
    the run unless each acknowledged storing it. A hospital not connected is not
    asked; transmitting again reaches it."""
    final_model = final_model_to_transmit(directory, run_id)
    state_dict = final_model.state_dict
    if state_dict is None:  # final_model_to_transmit refuses one without; for the type
        raise FileNotFoundError(f"There is no final model of run {run_id}.")
    node_ids = list(grid.get_node_ids())
    # No timeout: Flower answers for a hospital that drops out with an error reply.
    replies = list(
        grid.send_and_receive(
            [
                Message(
                    content=RecordDict(
                        {
                            "arrays": ArrayRecord(state_dict),
                            "federated": MetricRecord(
                                dict[str, int | float | list[int] | list[float]](
                                    final_model.federated
                                )
                            ),
                            "final-model": ConfigRecord({"run-id": str(run_id)}),
                        }
                    ),
                    dst_node_id=node_id,
                    message_type="query.receive",
                )
                for node_id in node_ids
            ]
        )
    )
    failure = transmission_failure(
        connected=len(node_ids),
        replied=len(replies),
        errors=sum(reply.has_error() for reply in replies),
    )
    if failure is not None:
        raise RuntimeError(f"Final model of run {run_id} not transmitted: {failure}")


def train(grid: Grid, context: Context, directory: Path) -> None:
    """Train with FedAvg and keep the final model at the startup (DS4); no hospital
    stores it until the data scientist transmits it."""
    fraction_evaluate = float(context.run_config["fraction-evaluate"])
    num_rounds = int(context.run_config["num-server-rounds"])
    lr = float(context.run_config["learning-rate"])

    torch.manual_seed(int(context.run_config["model-seed"]))
    arrays = ArrayRecord(Net().state_dict())
    strategy = FedAvg(fraction_evaluate=fraction_evaluate)
    result = strategy.start(
        grid=grid,
        initial_arrays=arrays,
        train_config=ConfigRecord({"lr": lr}),
        num_rounds=num_rounds,
    )

    # Only the federated aggregate of the last round; no hospital's own metrics.
    last_round = max(result.evaluate_metrics_clientapp, default=None)
    federated = (
        result.evaluate_metrics_clientapp[last_round]
        if last_round is not None
        else MetricRecord()
    )
    # No threshold: each hospital's laboratory director chooses one
    # (features/deployment.feature).
    keep_final_model(
        directory,
        run_id=context.run_id,
        state_dict=result.arrays.to_torch_state_dict(),
        federated={
            name: float(value)
            for name, value in federated.items()
            if isinstance(value, (int, float))
        },
        run_configuration=training_parameters(context.run_config),
        stored_at=datetime.now(UTC),
    )

    # Log the strategy metrics only when a W&B API key has been configured.
    wandb_api_key = str(context.run_config.get("wandb-api-key", "")).strip()
    if wandb_api_key:
        _log_result_to_wandb(result, wandb_api_key)
