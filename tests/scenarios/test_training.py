"""Scenarios: the startup's training runs (features/training.feature)."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from flwr.common.constant import Status, SubStatus
from pytest_bdd import given, parsers, scenarios, then, when

from tests.conftest import World

NOW = datetime(2026, 10, 30, 9, 0, tzinfo=UTC)
pytestmark = pytest.mark.django_db

scenarios("training.feature")


def keep(directory: Path, run_id: str, auroc: float, at: datetime) -> None:
    from iron_deficiency.final_models import keep_final_model
    from iron_deficiency.task import Net

    keep_final_model(
        directory,
        run_id=int(run_id),
        state_dict=Net().state_dict(),
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
        'the ServerApp keeps the final model of run "{run_id}" with AUROC across'
        " hospitals {auroc:f}"
    )
)
def server_app_keeps(world: World, run_id: str, auroc: float) -> None:
    keep(world["final_models_dir"], run_id, auroc, NOW)


@given(
    parsers.parse(
        'the startup kept the final model of run "{run_id}" at {day:d} Oct 2026,'
        " {hour:d}:{minute:d}"
    )
)
def startup_kept(world: World, run_id: str, day: int, hour: int, minute: int) -> None:
    at = datetime(2026, 10, day, hour, minute, tzinfo=UTC)
    keep(world["final_models_dir"], run_id, 0.85, at)


def listed(world: World) -> list[str]:
    from web.training.final_models import final_models

    return [model.run_id for model in final_models(world["final_models_dir"])]


@then(parsers.re(r"the startup's final models are (?P<run_ids>.+)$"))
def final_models_are(world: World, run_ids: str) -> None:
    expected = (
        [] if run_ids == "none" else [run.strip('" ') for run in run_ids.split(",")]
    )
    assert listed(world) == expected


@then(parsers.parse('final model "{run_id}" shows AUROC across hospitals {auroc:f}'))
def final_model_shows(world: World, run_id: str, auroc: float) -> None:
    from web.training.final_models import final_models

    model = next(
        model
        for model in final_models(world["final_models_dir"])
        if model.run_id == run_id
    )
    assert model.federated_auroc == auroc


@pytest.fixture
def superlink(monkeypatch: pytest.MonkeyPatch) -> World:
    """Stands in for `flwr run`: records each command, answers as Flower does."""
    import json
    import subprocess

    state: World = {
        "commands": [],
        "answer": {"success": True, "run-id": "7"},
        "hangs": False,
        # What `flwr ls` answers: the runs, as its JSON lists them.
        "runs": [],
        "listing": None,
    }

    def run(command: list[str], **kwargs: Any) -> "subprocess.CompletedProcess[str]":
        state["commands"].append(command)
        state["timeout"] = kwargs.get("timeout")
        if state["hangs"]:
            raise subprocess.TimeoutExpired(command, kwargs.get("timeout") or 0)
        answer = state["answer"]
        if command[1] == "ls":
            answer = state["listing"] or {"success": True, "runs": state["runs"]}
        return subprocess.CompletedProcess(command, 0, json.dumps(answer), "")

    monkeypatch.setattr(subprocess, "run", run)
    return state


@given("the SuperLink refuses runs")
def superlink_refuses(superlink: World) -> None:
    superlink["answer"] = {
        "success": False,
        "error-message": "Run submission failed",
    }


@given("the SuperLink does not answer")
def superlink_hangs(superlink: World) -> None:
    superlink["hangs"] = True


@then(parsers.parse("the submission waited at most {seconds:d} seconds"))
def waited_at_most(superlink: World, seconds: int) -> None:
    assert superlink["timeout"] is not None
    assert superlink["timeout"] <= seconds


@when("the data scientist submits a training run")
def submit(world: World, superlink: World) -> None:
    from django.core.exceptions import ValidationError

    from web.training.runs import submit_run

    try:
        world["run_id"] = submit_run()
    except ValidationError as error:
        world["error"] = error


@then("the SuperLink receives a run without a screening threshold")
def superlink_receives(superlink: World) -> None:
    [command] = superlink["commands"]
    assert "run" in command
    # The key the ServerApp read the threshold from.
    assert not any("screening-threshold" in part for part in command)


@then("the submission gives the run's ID")
def gives_run_id(world: World) -> None:
    assert world["run_id"] == 7


@then(parsers.parse('the submission is refused with code "{code}"'))
def refused(world: World, code: str) -> None:
    errors = world["error"].error_dict
    assert [error.code for error in errors["__all__"]] == [code]


@when(parsers.parse('the startup downloads final model "{run_id}" for sale'))
def download_for_sale(world: World, run_id: str) -> None:
    from web.training.final_models import for_sale

    world["download"] = for_sale(world["final_models_dir"], run_id)


@then("the download holds the final model's weights")
def weights(world: World) -> None:
    from iron_deficiency.screening import from_bytes
    from iron_deficiency.task import Net

    model = from_bytes(world["download"])
    assert model.state_dict is not None
    assert set(model.state_dict) == set(Net().state_dict())


@then(
    "it holds no threshold, no standardization and no metrics: the buyer chooses"
    " and standardizes on its own cohort"
)
def nothing_else(world: World) -> None:
    import io

    import torch

    assert set(torch.load(io.BytesIO(world["download"]))) == {"state_dict"}


@then("there is nothing to download")
def nothing_to_download(world: World) -> None:
    assert world["download"] is None


def flower_run(run_id: str, status: str, **times: str) -> dict[str, Any]:
    """One run as `flwr ls --format json` lists it."""
    return {
        "run-id": run_id,
        "status": status,
        "status-details": times.pop("details", "N/A"),
        "elapsed": 60.0,
        **{
            f"{state}-at": times.get(state, "N/A")
            for state in ("pending", "starting", "running", "finished")
        },
    }


@given("the SuperLink knows the runs:")
def superlink_knows(superlink: World, datatable: list[list[str]]) -> None:
    header, *rows = datatable
    for row in rows:
        cells = dict(zip(header, (cell.strip() for cell in row), strict=True))
        superlink["runs"].append(
            flower_run(
                cells["run"],
                cells["status"],
                pending=cells["pending at"],
                running=cells["running at"],
                finished=cells["finished at"],
            )
        )


@given(
    parsers.parse('the SuperLink knows run "{run_id}" failed with details "{details}"')
)
def superlink_knows_failed(superlink: World, run_id: str, details: str) -> None:
    superlink["runs"].append(
        flower_run(
            run_id,
            "finished:failed",
            pending="2026-10-30 14:01:00Z",
            running="2026-10-30 14:02:00Z",
            finished="2026-10-30 14:03:00Z",
            details=details,
        )
    )


@given("the SuperLink answers that it is unavailable")
def superlink_unavailable(superlink: World) -> None:
    superlink["listing"] = {
        "success": False,
        "error-message": "Connection to the SuperLink is unavailable.",
    }


@then("the training runs are:")
def training_runs_are(superlink: World, datatable: list[list[str]]) -> None:
    from web.training.runs import training_runs

    header, *rows = datatable
    expected = [
        dict(zip(header, (cell.strip() for cell in row), strict=True)) for row in rows
    ]
    listed = [
        {
            "run": str(run.run_id),
            "status": run.status_label,
            "since": run.since.strftime("%Y-%m-%d %H:%M") if run.since else "",
        }
        for run in training_runs()
    ]
    assert listed == expected


@then(parsers.parse('training run "{run_id}" is "{status}", with details "{details}"'))
def training_run_is(superlink: World, run_id: str, status: str, details: str) -> None:
    from web.training.runs import training_runs

    (run,) = [run for run in training_runs() if str(run.run_id) == run_id]
    assert (run.status_label, run.details) == (status, details)


@when("the data scientist looks at the training runs")
def look_at_runs(world: World, superlink: World) -> None:
    from django.core.exceptions import ValidationError

    from web.training.runs import training_runs

    try:
        world["runs"] = training_runs()
    except ValidationError as error:
        world["error"] = error


@then(parsers.parse('looking is refused with code "{code}"'))
def looking_refused(world: World, code: str) -> None:
    assert world["error"].code == code


def constants(holder: type) -> list[str]:
    """A Flower constants class's values, as `flwr ls` prints them."""
    return [value for name, value in vars(holder).items() if name.isupper()]


FLOWER_STATUSES = [
    status for status in constants(Status) if status != Status.FINISHED
] + [f"{Status.FINISHED}:{sub_status}" for sub_status in constants(SubStatus)]


@pytest.mark.parametrize("status_text", FLOWER_STATUSES)
def test_every_status_flower_reports_has_a_label(status_text: str) -> None:
    from web.training.runs import TrainingRun

    run = TrainingRun.from_flower(flower_run("3", status_text))
    assert run.status is not None
    assert run.status_label == run.status.label


def test_a_status_flower_adds_later_shows_as_flower_names_it() -> None:
    from web.training.runs import TrainingRun

    run = TrainingRun.from_flower(flower_run("3", "finished:archived"))
    assert (run.status, run.status_label) == (None, "finished:archived")
