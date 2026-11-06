"""Scenarios: the startup's training runs (features/startup/training.feature)."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from tests.conftest import World

NOW = datetime(2026, 10, 30, 9, 0, tzinfo=UTC)
pytestmark = pytest.mark.django_db

scenarios("startup/training.feature")


def keep(directory: Path, run_id: str, auroc: float, at: datetime) -> None:
    from ml.final_model import Net
    from ml.training import keep_final_model

    keep_final_model(
        directory,
        run_id=int(run_id),
        state_dict=Net().state_dict(),
        federated={"eval_auroc": auroc},
        run_configuration={"num-server-rounds": 3, "batch-size": 64},
        stored_at=at,
    )


@given(parsers.parse('data scientist "{name}"'))
def data_scientist(world: World, db: None, name: str, tmp_path: Path) -> None:
    from tests.startup.conftest import make_data_scientist

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
    from web.startup.training.final_models import final_models

    return [model.run_id for model in final_models(world["final_models_dir"])]


@then(parsers.re(r"the startup's final models are (?P<run_ids>.+)$"))
def final_models_are(world: World, run_ids: str) -> None:
    expected = (
        [] if run_ids == "none" else [run.strip('" ') for run in run_ids.split(",")]
    )
    assert listed(world) == expected


@then(parsers.parse('final model "{run_id}" shows AUROC across hospitals {auroc:f}'))
def final_model_shows(world: World, run_id: str, auroc: float) -> None:
    from web.startup.training.final_models import final_models

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
        # What `flwr stop` answers, when not that it stopped the run.
        "stop_answer": None,
    }

    def run(command: list[str], **kwargs: Any) -> "subprocess.CompletedProcess[str]":
        state["commands"].append(command)
        state["timeout"] = kwargs.get("timeout")
        if state["hangs"]:
            raise subprocess.TimeoutExpired(command, kwargs.get("timeout") or 0)
        answer = state["answer"]
        if command[1] == "stop":
            answer = state["stop_answer"] or {"success": True, "run-id": command[2]}
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
    submit_form(world, {})


@then("the SuperLink receives a run without a screening threshold")
def superlink_receives(superlink: World) -> None:
    [command] = superlink["commands"]
    assert "run" in command
    # The key the ServerApp read the threshold from.
    assert not any("screening-threshold" in part for part in command)


def submit_form(world: World, data: dict[str, str]) -> None:
    """Submit through the form, as the page does: defaults for what is not given."""
    from django.core.exceptions import ValidationError

    from web.startup.training.forms import SubmitRunForm
    from web.startup.training.runs import submit_run

    form = SubmitRunForm({**SubmitRunForm.defaults(), **data})
    world["form"] = form
    if not form.is_valid():
        return
    try:
        world["run_id"] = submit_run(form.run_configuration())
    except ValidationError as error:
        world["error"] = error


def field_named(label: str) -> str:
    """The form field a scenario names by its label."""
    from web.startup.training.forms import SubmitRunForm

    return next(
        name
        for name, field in SubmitRunForm.base_fields.items()
        if str(field.label).lower() == label
    )


@when("the data scientist submits a training run with:")
def submit_with(world: World, superlink: World, datatable: list[list[str]]) -> None:
    labels, values = datatable
    submit_form(
        world,
        {
            field_named(label): value
            for label, value in zip(labels, values, strict=True)
        },
    )


@when(
    parsers.re(
        r"the data scientist submits a training run with (?P<label>[a-z ]+)"
        r" (?P<value>-?[0-9.]+)$"
    )
)
def submit_one(world: World, superlink: World, label: str, value: str) -> None:
    submit_form(world, {field_named(label): value})


def run_configuration_sent(superlink: World) -> dict[str, Any]:
    """The run configuration `flwr run` was given: space-separated TOML pairs, as
    Flower reads them (importing Flower here warns, which -W error fails)."""
    import tomllib

    [command] = superlink["commands"]
    pairs = command[command.index("--run-config") + 1].split()
    return tomllib.loads("\n".join(pairs))


@then("the SuperLink receives the run configuration:")
def receives_configuration(superlink: World, datatable: list[list[str]]) -> None:
    sent = run_configuration_sent(superlink)
    for key, value in datatable[1:]:
        assert str(sent[key]) == value, (key, sent)


@then("the run configuration sets no fraction of hospitals evaluating and no W&B key")
def sets_nothing_else(superlink: World) -> None:
    sent = run_configuration_sent(superlink)
    assert "fraction-evaluate" not in sent
    assert "wandb-api-key" not in sent


@then(
    parsers.re(
        r'the run configuration is refused on (?P<label>[a-z ]+) with code "(?P<code>.+)"'
    )
)
def configuration_refused(world: World, label: str, code: str) -> None:
    errors = world["form"].errors.as_data()
    assert [error.code for error in errors[field_named(label)]] == [code]


@then("the SuperLink receives no run")
def receives_no_run(superlink: World) -> None:
    assert not [command for command in superlink["commands"] if command[1] == "run"]


@when(
    parsers.parse(
        'the ServerApp keeps the final model of run "{run_id}" trained with run'
        " configuration:"
    )
)
def server_app_keeps_configured(
    world: World, run_id: str, datatable: list[list[str]]
) -> None:
    import tomllib

    from ml.final_model import Net
    from ml.training import keep_final_model, training_parameters

    run_config = {
        key: value
        if key in ("demo-dir", "wandb-api-key")
        else tomllib.loads(f"v = {value}")["v"]
        for key, value in datatable[1:]
    }
    keep_final_model(
        world["final_models_dir"],
        run_id=int(run_id),
        state_dict=Net().state_dict(),
        federated={"eval_auroc": 0.86},
        run_configuration=training_parameters(run_config),
        stored_at=NOW,
    )


@then(parsers.parse('final model "{run_id}" shows run configuration "{shown}"'))
def shows_configuration(world: World, run_id: str, shown: str) -> None:
    from web.startup.training.final_models import final_models

    [model] = [
        model
        for model in final_models(world["final_models_dir"])
        if model.run_id == run_id
    ]
    assert model.run_configuration_shown == shown


@then(
    parsers.parse(
        'the startup\'s copy of final model "{run_id}" holds no W&B key and no folder'
    )
)
def holds_no_secret(world: World, run_id: str) -> None:
    from ml.final_model import final_model_path, read

    kept = read(final_model_path(world["final_models_dir"], run_id))
    assert "wandb-api-key" not in kept.run_configuration
    assert "demo-dir" not in kept.run_configuration


@then("the submission gives the run's ID")
def gives_run_id(world: World) -> None:
    assert world["run_id"] == 7


@then(parsers.parse('the submission is refused with code "{code}"'))
def refused(world: World, code: str) -> None:
    errors = world["error"].error_dict
    assert [error.code for error in errors["__all__"]] == [code]


@when(parsers.parse('the startup downloads final model "{run_id}" for sale'))
def download_for_sale(world: World, run_id: str) -> None:
    from web.startup.training.final_models import for_sale

    world["download"] = for_sale(world["final_models_dir"], run_id)


@then("the download holds the final model's weights")
def weights(world: World) -> None:
    from ml.final_model import Net, from_bytes

    model = from_bytes(world["download"])
    assert model.state_dict is not None
    assert set(model.state_dict) == set(Net().state_dict())


@then(
    "it holds no threshold, no standardization, no metrics and no run"
    " configuration: the buyer chooses and standardizes on its own cohort"
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
    from web.startup.training.runs import training_runs

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
    from web.startup.training.runs import training_runs

    (run,) = [run for run in training_runs() if str(run.run_id) == run_id]
    assert (run.status_label, run.details) == (status, details)


@when("the data scientist looks at the training runs")
def look_at_runs(world: World, superlink: World) -> None:
    from django.core.exceptions import ValidationError

    from web.startup.training.runs import training_runs

    try:
        world["runs"] = training_runs()
    except ValidationError as error:
        world["error"] = error


@then(parsers.parse('looking is refused with code "{code}"'))
def looking_refused(world: World, code: str) -> None:
    assert world["error"].code == code


# What `flwr ls` reports (Flower 1.40, flwr.common.constant Status and SubStatus).
# Importing Flower here would raise Click's DeprecationWarning under -W error.
FLOWER_STATUSES = [
    "pending",
    "starting",
    "running",
    "finished:completed",
    "finished:failed",
    "finished:stopped",
]


@pytest.mark.parametrize("status_text", FLOWER_STATUSES)
def test_every_status_flower_reports_has_a_label(status_text: str) -> None:
    from web.startup.training.runs import TrainingRun

    run = TrainingRun.from_flower(flower_run("3", status_text))
    assert run.status is not None
    assert run.status_label == run.status.label


def test_a_status_flower_adds_later_shows_as_flower_names_it() -> None:
    from web.startup.training.runs import TrainingRun

    run = TrainingRun.from_flower(flower_run("3", "finished:archived"))
    assert (run.status, run.status_label) == (None, "finished:archived")


@pytest.mark.parametrize("status", FLOWER_STATUSES)
def test_only_an_unfinished_run_is_in_progress(status: str) -> None:
    from web.startup.training.runs import RunStatus

    assert RunStatus(status).in_progress == (not status.startswith("finished:"))


@given(parsers.parse('the SuperLink knows run "{run_id}" is running'))
def superlink_knows_running(superlink: World, run_id: str) -> None:
    superlink["runs"] = [flower_run(run_id, "running")]


@given("the SuperLink refuses to stop it")
def superlink_refuses_stop(superlink: World) -> None:
    superlink["stop_answer"] = {
        "success": False,
        "error-message": "Run 7 couldn't be stopped.",
    }


@when(parsers.parse('the data scientist stops training run "{run_id}"'))
def stop(world: World, superlink: World, run_id: str) -> None:
    from django.core.exceptions import ValidationError

    from web.startup.training.runs import stop_run

    try:
        stop_run(int(run_id))
    except ValidationError as error:
        world["error"] = error


@then(parsers.parse('the SuperLink is asked to stop run "{run_id}"'))
def asked_to_stop(superlink: World, run_id: str) -> None:
    stops = [command for command in superlink["commands"] if command[1] == "stop"]
    assert [command[2] for command in stops] == [run_id]


@then(parsers.parse('stopping is refused with code "{code}"'))
def stopping_refused(world: World, code: str) -> None:
    assert world["error"].code == code


@when(
    parsers.parse(
        'the data scientist transmits final model "{run_id}" to the hospitals'
    )
)
def transmit(world: World, superlink: World, run_id: str) -> None:
    from django.core.exceptions import ValidationError

    from web.startup.training.models import Transmission

    superlink["answer"] = {"success": True, "run-id": "8"}
    try:
        world["transmission"] = Transmission.objects.transmit(
            final_model=run_id, transmitted_by=world["data_scientist"], now=NOW
        )
    except ValidationError as error:
        world["error"] = error


@then(
    parsers.parse(
        'the SuperLink receives a run with run configuration "{key}" {value:d}'
    )
)
def receives_run_with(superlink: World, key: str, value: int) -> None:
    # A string: Flower's run IDs exceed TOML's integers.
    assert run_configuration_sent(superlink)[key] == str(value)


@then(
    parsers.parse(
        'the startup records that run "{run_id}" transmits final model "{final_model}",'
        ' transmitted by "{name}"'
    )
)
def records_transmission(
    world: World, run_id: str, final_model: str, name: str
) -> None:
    from web.startup.training.models import Transmission

    transmission = Transmission.objects.get()
    assert (transmission.run_id, transmission.final_model) == (run_id, final_model)
    assert transmission.transmitted_by.username == name.lower().replace(" ", "-")
    assert transmission.submitted_at == NOW


@when(parsers.parse('the ServerApp reads final model "{run_id}" to transmit'))
def server_app_reads(world: World, run_id: str) -> None:
    from ml.training import final_model_to_transmit

    try:
        world["to_send"] = final_model_to_transmit(
            world["final_models_dir"], int(run_id)
        )
    except FileNotFoundError as error:
        world["error"] = error


@then(
    parsers.parse(
        "it transmits the weights, the AUROC across hospitals and run ID {run_id:d}"
    )
)
def transmits_what(world: World, run_id: int) -> None:
    to_send = world["to_send"]
    assert to_send.state_dict is not None
    assert to_send.federated == {"eval_auroc": 0.85}
    assert to_send.run_id == run_id


@then("it transmits no run configuration")
def transmits_no_configuration(world: World) -> None:
    assert world["to_send"].run_configuration == {}


@then(
    parsers.parse("transmitting is refused: there is no final model of run {run_id:d}")
)
def transmitting_refused(world: World, run_id: int) -> None:
    assert str(world["error"]) == f"There is no final model of run {run_id}."


@given(
    parsers.parse(
        'the data scientist transmitted final model "{final_model}" in run "{run_id}"'
    )
)
def transmitted_before(world: World, final_model: str, run_id: str) -> None:
    from web.startup.training.models import Transmission

    Transmission.objects.create(
        final_model=final_model,
        run_id=run_id,
        transmitted_by=world["data_scientist"],
        submitted_at=NOW,
    )


@given(parsers.parse('the SuperLink knows run "{run_id}" is "{status}"'))
def superlink_knows_status(superlink: World, run_id: str, status: str) -> None:
    superlink["runs"] = [flower_run(run_id, status)]


def transmission_status_of(world: World, run_id: str) -> Any:
    from web.startup.training.final_models import final_models, transmission_statuses
    from web.startup.training.models import Transmission
    from web.startup.training.runs import training_runs

    kept = final_models(world["final_models_dir"])
    return transmission_statuses(
        kept, training_runs(), list(Transmission.objects.all())
    )[run_id]


@then(parsers.parse('final model "{run_id}" shows "{shown}"'))
def final_model_shows_transmission_status(
    world: World, superlink: World, run_id: str, shown: str
) -> None:
    assert transmission_status_of(world, run_id).label == shown


@then(
    parsers.re(
        r'final model "(?P<run_id>\d+)" (?P<offers>offers|does not offer) Transmit to hospitals'
    )
)
def offers_send(world: World, superlink: World, run_id: str, offers: str) -> None:
    assert transmission_status_of(world, run_id).offers_transmit is (offers == "offers")


@when(
    parsers.parse(
        "{replied:d} of {connected:d} connected hospitals reply,"
        " {errors:d} of them with an error"
    )
)
def hospitals_reply(world: World, replied: int, connected: int, errors: int) -> None:
    from ml.training import transmission_failure

    world["failure"] = transmission_failure(
        connected=connected, replied=replied, errors=errors
    )


@then(parsers.parse('the transmission fails with "{why}"'))
def transmission_fails(world: World, why: str) -> None:
    assert world["failure"] == why


@then("the transmission succeeds")
def transmission_succeeds(world: World) -> None:
    assert world["failure"] is None


@pytest.mark.parametrize("status", FLOWER_STATUSES)
def test_every_run_status_shows_a_transmission_status(status: str) -> None:
    from web.startup.training.final_models import TransmissionStatus
    from web.startup.training.runs import RunStatus

    assert isinstance(TransmissionStatus.of_run(RunStatus(status)), TransmissionStatus)
