"""ServerApp for federated iron-deficiency classification."""

from flwr.app import ArrayRecord, ConfigRecord, Context
from flwr.serverapp import Grid, ServerApp
from flwr.serverapp.strategy import FedAvg, Result

from iron_deficiency.task import Net

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
            metrics = {"round": round_number}
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
    """Main entry point for the ServerApp."""

    # Read run config
    fraction_evaluate: float = context.run_config["fraction-evaluate"]
    num_rounds: int = context.run_config["num-server-rounds"]
    lr: float = context.run_config["learning-rate"]

    # Load global model
    global_model = Net()
    arrays = ArrayRecord(global_model.state_dict())

    # Initialize FedAvg strategy
    strategy = FedAvg(fraction_evaluate=fraction_evaluate)

    # Start strategy, run FedAvg for `num_rounds`
    result = strategy.start(
        grid=grid,
        initial_arrays=arrays,
        train_config=ConfigRecord({"lr": lr}),
        num_rounds=num_rounds,
    )

    # Log the strategy metrics only when a W&B API key has been configured.
    wandb_api_key = str(context.run_config.get("wandb-api-key", "")).strip()
    if wandb_api_key:
        _log_result_to_wandb(result, wandb_api_key)
