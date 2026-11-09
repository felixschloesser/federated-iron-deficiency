"""The ServerApp: runs federated training with the hospitals and keeps the final
model at the startup."""

import os
from datetime import UTC, datetime
from logging import INFO
from pathlib import Path

import torch
from flwr.app import (
    ArrayRecord,
    ConfigRecord,
    Context,
)
from flwr.common.logger import log
from flwr.serverapp import Grid, ServerApp
from flwr.serverapp.strategy import FedAvg, Result

from ml.final_model import Net
from ml.training import (
    keep_final_model,
    startup_final_models,
    training_parameters,
)

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
    """Run one training run and keep its final model in the startup's folder."""
    training_run(grid, context, startup_final_models(os.environ))


def training_run(grid: Grid, context: Context, directory: Path | None) -> None:
    """Train with FedAvg and keep the final model in `directory` at the startup,
    or nowhere if None. No hospital stores it until the data scientist releases
    it and the hospital fetches it."""
    fraction_evaluate = float(context.run_config["fraction-evaluate"])
    num_rounds = int(context.run_config["num-server-rounds"])
    lr = float(context.run_config["learning-rate"])

    torch.manual_seed(int(context.run_config["model-seed"]))
    arrays = ArrayRecord(Net().state_dict())
    # TODO(issue A, DD5): aggregate through SecAggPlusWorkflow, so the ServerApp
    # receives only masked updates; tests/quality/privacy/test_updates.py.
    strategy = FedAvg(fraction_evaluate=fraction_evaluate)
    result = strategy.start(
        grid=grid,
        initial_arrays=arrays,
        train_config=ConfigRecord({"lr": lr}),
        num_rounds=num_rounds,
    )

    # Keep only the last round's AUROC aggregated across hospitals, never one
    # hospital's own metrics. A run without evaluation metrics raises here
    # (KeyError or ValueError) and keeps no final model.
    last_round = max(result.evaluate_metrics_clientapp)
    federated_auroc = result.evaluate_metrics_clientapp[last_round]["eval_auroc"]
    if not isinstance(federated_auroc, (int, float)):
        raise TypeError(f"The AUROC across hospitals is no number: {federated_auroc}")
    # No threshold: each hospital's laboratory director chooses one.
    if directory is None:
        log(INFO, "FINAL_MODELS_DIR is not set: no final model kept.")
    else:
        keep_final_model(
            directory,
            run_id=context.run_id,
            state_dict=result.arrays.to_torch_state_dict(),
            federated_auroc=float(federated_auroc),
            run_configuration=training_parameters(context.run_config),
            stored_at=datetime.now(UTC),
        )

    # Log the strategy metrics only when a W&B API key has been configured.
    wandb_api_key = str(context.run_config.get("wandb-api-key", "")).strip()
    if wandb_api_key:
        _log_result_to_wandb(result, wandb_api_key)
