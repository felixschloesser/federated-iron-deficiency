"""Scenarios: the startup's training runs (features/training.feature)."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from tests.conftest import World

NOW = datetime(2026, 10, 30, 9, 0, tzinfo=UTC)
pytestmark = pytest.mark.django_db

scenarios("training.feature")


def keep(
    directory: Path, run_id: str, threshold: float, auroc: float, at: datetime
) -> None:
    from iron_deficiency.final_models import keep_final_model
    from iron_deficiency.task import Net

    keep_final_model(
        directory,
        run_id=int(run_id),
        state_dict=Net().state_dict(),
        threshold=threshold,
        federated={"eval_auroc": auroc},
        stored_at=at,
    )


@given(parsers.parse('data scientist "{name}"'))
def data_scientist(world: World, db: None, name: str, tmp_path: Path) -> None:
    from tests.conftest import make_data_scientist

    world["data_scientist"] = make_data_scientist(name)
    world["final_models_dir"] = tmp_path / "final-models"


@when(
    parsers.parse(
        'the ServerApp keeps the final model of run "{run_id}" with threshold'
        " {threshold:f} and AUROC across hospitals {auroc:f}"
    )
)
def server_app_keeps(world: World, run_id: str, threshold: float, auroc: float) -> None:
    keep(world["final_models_dir"], run_id, threshold, auroc, NOW)


@given(
    parsers.parse(
        'the startup kept the final model of run "{run_id}" at {day:d} Oct 2026,'
        " {hour:d}:{minute:d}"
    )
)
def startup_kept(world: World, run_id: str, day: int, hour: int, minute: int) -> None:
    at = datetime(2026, 10, day, hour, minute, tzinfo=UTC)
    keep(world["final_models_dir"], run_id, 0.5, 0.85, at)


def listed(world: World) -> list[str]:
    from web.training.final_models import final_models

    return [model.run_id for model in final_models(world["final_models_dir"])]


@then(parsers.re(r"the startup's final models are (?P<run_ids>.+)$"))
def final_models_are(world: World, run_ids: str) -> None:
    expected = (
        [] if run_ids == "none" else [run.strip('" ') for run in run_ids.split(",")]
    )
    assert listed(world) == expected


@then(
    parsers.parse(
        'final model "{run_id}" shows threshold {threshold:f} and AUROC across'
        " hospitals {auroc:f}"
    )
)
def final_model_shows(
    world: World, run_id: str, threshold: float, auroc: float
) -> None:
    from web.training.final_models import final_models

    model = next(
        model
        for model in final_models(world["final_models_dir"])
        if model.run_id == run_id
    )
    assert (model.threshold, model.federated_auroc) == (threshold, auroc)
