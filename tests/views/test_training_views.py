"""Views of the startup's training runs: who may, what the Training runs page shows."""

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
from django.contrib.messages import get_messages
from django.test import Client
from django.urls import reverse
from pytest_django import DjangoAssertNumQueries
from pytest_django.asserts import assertContains, assertNotContains, assertRedirects
from pytest_django.fixtures import Settings

from ml.final_models import keep_final_model
from ml.task import Net
from tests.conftest import make_data_scientist, make_laboratory_director
from web.training.forms import SubmitRunForm

pytestmark = pytest.mark.django_db


@pytest.fixture
def final_models_dir(tmp_path: Path, settings: Settings) -> Path:
    directory = tmp_path / "final-models"
    settings.FINAL_MODELS_DIR = directory
    keep_final_model(
        directory,
        run_id=7,
        state_dict=Net().state_dict(),
        federated={"eval_auroc": 0.861},
        stored_at=datetime(2026, 10, 30, 9, 0, tzinfo=UTC),
    )
    return directory


def test_final_models_page(
    client: Client,
    final_models_dir: Path,
    django_assert_num_queries: DjangoAssertNumQueries,
) -> None:
    client.force_login(make_data_scientist("Data One"))
    # Session, user with role, transmissions.
    with django_assert_num_queries(3):
        response = client.get(reverse("training:runs"))
    for cell in (
        '<td data-label="Stored">30 Oct 2026, 10:00</td>',
        '<td data-label="AUROC across hospitals">0.86</td>',
        '<td data-label="Run configuration">—</td>',
        (
            '<td data-label="Model sale"><a href="/training/runs/7/for-sale/" download'
            ' aria-label="Download final model of run 7 for sale">Download for sale</a>'
            "</td>"
        ),
    ):
        assertContains(response, cell, html=True)


def test_a_laboratory_director_is_sent_to_their_own_page(client: Client) -> None:
    client.force_login(make_laboratory_director("Director One"))
    response = client.get(reverse("training:runs"))
    assertRedirects(response, reverse("deployment:models"))


def answering(
    monkeypatch: pytest.MonkeyPatch,
    answer: dict[str, object],
    listing: dict[str, object] | None = None,
) -> None:
    """`flwr run` and `flwr ls` answering as Flower's JSON output does."""

    def run(command: list[str], **kwargs: object) -> "subprocess.CompletedProcess[str]":
        said = (
            (listing or {"success": True, "runs": []}) if command[1] == "ls" else answer
        )
        return subprocess.CompletedProcess(command, 0, json.dumps(said), "")

    monkeypatch.setattr(subprocess, "run", run)


@pytest.fixture(autouse=True)
def superlink(monkeypatch: pytest.MonkeyPatch) -> None:
    """No page here reaches a real SuperLink: one that knows no runs yet."""
    answering(monkeypatch, {"success": True, "run-id": "7"})


RUNNING = {
    "run-id": "7",
    "status": "running",
    "status-details": "N/A",
    "elapsed": 61.0,
    "pending-at": "2026-10-30 14:01:00Z",
    "starting-at": "2026-10-30 14:01:30Z",
    "running-at": "2026-10-30 14:02:00Z",
    "finished-at": "N/A",
}


@pytest.mark.usefixtures("data_scientist")
def test_the_page_shows_each_training_runs_status(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    answering(monkeypatch, {}, {"success": True, "runs": [RUNNING]})
    response = client.get(reverse("training:runs"))
    for cell in (
        '<td data-label="Run">7</td>',
        '<td data-label="Status" class="no-wrap"><strong>Running</strong></td>',
        '<td data-label="Since" class="no-wrap">30 Oct 2026, 15:02</td>',
        '<td data-label="Elapsed" class="no-wrap">0:01:01</td>',
        '<td data-label="Details">—</td>',
    ):
        assertContains(response, cell, html=True)
    assertContains(response, "reload the page")


@pytest.mark.usefixtures("data_scientist")
def test_without_the_superlink_the_page_says_the_statuses_are_unknown(
    client: Client, monkeypatch: pytest.MonkeyPatch, final_models_dir: Path
) -> None:
    answering(
        monkeypatch,
        {},
        {"success": False, "error-message": "Connection to 127.0.0.1:9093 unavailable"},
    )
    response = client.get(reverse("training:runs"))
    assertContains(response, "the training runs&#x27; statuses are unknown")
    assertNotContains(response, "127.0.0.1")
    # The final models still show.
    assertContains(response, 'href="/training/runs/7/for-sale/"')


@pytest.mark.usefixtures("data_scientist")
def test_a_submission_without_an_answer_points_to_the_training_runs(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    def run(command: list[str], **kwargs: object) -> "subprocess.CompletedProcess[str]":
        if command[1] == "ls":
            return subprocess.CompletedProcess(
                command, 0, json.dumps({"success": True, "runs": []}), ""
            )
        raise subprocess.TimeoutExpired(command, 20)

    monkeypatch.setattr(subprocess, "run", run)
    response = client.post(reverse("training:runs"), SubmitRunForm.defaults())
    assertContains(response, "check the training runs below before submitting again")


@pytest.fixture
def data_scientist(client: Client) -> None:
    client.force_login(make_data_scientist("Data One"))


@pytest.mark.usefixtures("data_scientist")
def test_submitting_a_run_redirects_to_the_final_models(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    answering(monkeypatch, {"success": True, "run-id": "7"})
    response = client.post(reverse("training:runs"), SubmitRunForm.defaults())
    assertRedirects(response, reverse("training:runs"))
    assert [str(message) for message in get_messages(response.wsgi_request)] == [
        "Training run 7 submitted. Its final model appears here when the run finishes."
    ]


@pytest.mark.usefixtures("data_scientist")
def test_a_refused_run_says_why(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    answering(monkeypatch, {"success": False, "error-message": "unavailable"})
    response = client.post(reverse("training:runs"), SubmitRunForm.defaults())
    assert response.status_code == 200
    errors = response.context["form"].errors.as_data()["__all__"]
    assert [error.code for error in errors] == ["superlink_refused"]
    assertContains(response, "The SuperLink refused the run: unavailable")


def test_a_deployment_tells_the_server_app_its_demo_folder(
    settings: Settings, tmp_path: Path
) -> None:
    from web.training.runs import run_configuration

    settings.DATA_DIR = tmp_path / "startup"
    assert (
        run_configuration({"batch-size": 64}) == f"batch-size=64 demo-dir='{tmp_path}'"
    )


@pytest.mark.usefixtures("data_scientist")
def test_a_run_without_an_answer_shows_no_server_paths(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    def run(command: list[str], **kwargs: object) -> "subprocess.CompletedProcess[str]":
        if command[1] == "ls":
            return subprocess.CompletedProcess(
                command, 0, json.dumps({"success": True, "runs": []}), ""
            )
        return subprocess.CompletedProcess(command, 1, "", "/srv/flwr-home/config.toml")

    monkeypatch.setattr(subprocess, "run", run)
    response = client.post(reverse("training:runs"), SubmitRunForm.defaults())
    assertContains(response, "The SuperLink refused the run: it gave no answer")
    assertNotContains(response, "/srv/flwr-home")


@pytest.mark.usefixtures("data_scientist")
def test_a_final_model_downloads_for_sale(
    client: Client, final_models_dir: Path
) -> None:
    from ml.screening import from_bytes

    response = client.get(reverse("training:for_sale", kwargs={"run_id": "7"}))
    assert response.status_code == 200
    assert response["Content-Disposition"] == (
        'attachment; filename="final-model-run-7.pt"'
    )
    assert from_bytes(response.content).state_dict is not None


@pytest.mark.usefixtures("data_scientist")
def test_a_run_without_a_final_model_is_not_found(
    client: Client, final_models_dir: Path
) -> None:
    response = client.get(reverse("training:for_sale", kwargs={"run_id": "9"}))
    assert response.status_code == 404


def test_only_the_data_scientist_downloads_for_sale(
    client: Client, final_models_dir: Path
) -> None:
    client.force_login(make_laboratory_director("Director One"))
    response = client.get(reverse("training:for_sale", kwargs={"run_id": "7"}))
    assertRedirects(response, reverse("deployment:models"))


@pytest.mark.usefixtures("data_scientist")
def test_each_final_model_links_to_its_sale(
    client: Client, final_models_dir: Path
) -> None:
    response = client.get(reverse("training:runs"))
    assertContains(
        response,
        f'href="{reverse("training:for_sale", kwargs={"run_id": "7"})}"',
    )


def test_every_offered_parameter_is_kept_with_the_final_model() -> None:
    from ml.final_models import TRAINING_PARAMETERS

    for name in SubmitRunForm.base_fields:
        assert name.replace("_", "-") in TRAINING_PARAMETERS


@pytest.mark.usefixtures("data_scientist")
def test_the_form_starts_at_the_apps_own_run_configuration(client: Client) -> None:
    response = client.get(reverse("training:runs"))
    assertContains(response, 'name="batch_size" value="64"')


@pytest.mark.usefixtures("data_scientist")
def test_only_a_run_in_progress_offers_stop(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    completed = {**RUNNING, "run-id": "6", "status": "finished:completed"}
    answering(monkeypatch, {}, {"success": True, "runs": [RUNNING, completed]})
    response = client.get(reverse("training:runs"))
    assertContains(response, 'action="/training/runs/7/stop/"')
    assertContains(response, 'aria-label="Stop run 7"')
    assertNotContains(response, 'action="/training/runs/6/stop/"')


@pytest.mark.usefixtures("data_scientist")
def test_stopping_a_run_returns_to_the_training_runs(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    answering(monkeypatch, {"success": True, "run-id": "7"})
    response = client.post(reverse("training:stop", kwargs={"run_id": 7}))
    assertRedirects(response, reverse("training:runs"))
    assert [str(message) for message in get_messages(response.wsgi_request)] == [
        "Training run 7 stopped."
    ]


@pytest.mark.usefixtures("data_scientist")
def test_a_refused_stop_says_why(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    answering(monkeypatch, {"success": False, "error-message": "no such run"})
    response = client.post(reverse("training:stop", kwargs={"run_id": 7}))
    assertRedirects(response, reverse("training:runs"))
    assert [str(message) for message in get_messages(response.wsgi_request)] == [
        "The SuperLink did not stop training run 7: no such run"
    ]


@pytest.mark.usefixtures("data_scientist")
def test_without_the_superlink_the_page_offers_no_submission(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    answering(monkeypatch, {}, {"success": False, "error-message": "unavailable"})
    response = client.get(reverse("training:runs"))
    assert response.context["submits"] is False
    assertNotContains(response, 'name="batch_size"')
    assertContains(
        response,
        "Submitting, stopping and transmitting come back when the SuperLink answers.",
    )


@pytest.mark.usefixtures("data_scientist")
def test_an_error_summary_takes_focus(client: Client) -> None:
    response = client.post(
        reverse("training:runs"), {**SubmitRunForm.defaults(), "batch_size": 16}
    )
    assertContains(response, 'tabindex="-1" autofocus')


@pytest.mark.usefixtures("data_scientist")
def test_each_cell_names_its_column_for_narrow_screens(
    client: Client, monkeypatch: pytest.MonkeyPatch, final_models_dir: Path
) -> None:
    answering(monkeypatch, {}, {"success": True, "runs": [RUNNING]})
    response = client.get(reverse("training:runs"))
    assertContains(response, '<td data-label="Run">7</td>', html=True)
    assertContains(response, '<td data-label="Run configuration">—</td>', html=True)


def test_a_file_not_named_after_a_run_is_no_final_model(
    final_models_dir: Path,
) -> None:
    from web.deployment.model_files import screening_models
    from web.training.final_models import final_models

    (final_models_dir / "7.pt").rename(final_models_dir / "run123.pt")
    assert final_models(final_models_dir) == []
    assert screening_models(final_models_dir) == []


@pytest.mark.usefixtures("data_scientist")
def test_a_final_model_not_transmitted_offers_transmit(
    client: Client, final_models_dir: Path
) -> None:
    response = client.get(reverse("training:runs"))
    assertContains(response, '<td data-label="Hospitals">Not transmitted', html=False)
    assertContains(response, 'action="/training/runs/7/transmit/"')
    assertContains(
        response, 'aria-label="Transmit final model of run 7 to the hospitals"'
    )


@pytest.mark.usefixtures("data_scientist")
def test_transmitting_a_final_model_returns_with_its_run(
    client: Client, monkeypatch: pytest.MonkeyPatch, final_models_dir: Path
) -> None:
    answering(monkeypatch, {"success": True, "run-id": "8"})
    response = client.post(reverse("training:transmit", kwargs={"run_id": "7"}))
    assertRedirects(response, reverse("training:runs"))
    assert [str(message) for message in get_messages(response.wsgi_request)] == [
        "Run 8 transmits final model of run 7 to every hospital connected now."
    ]


@pytest.mark.usefixtures("data_scientist")
def test_a_run_that_transmits_a_final_model_says_so(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    from web.training.models import Transmission

    Transmission.objects.create(
        final_model="7",
        run_id="8",
        transmitted_by=make_data_scientist("Data Two"),
        submitted_at=datetime(2026, 10, 30, 9, 0, tzinfo=UTC),
    )
    answering(monkeypatch, {}, {"success": True, "runs": [{**RUNNING, "run-id": "8"}]})
    response = client.get(reverse("training:runs"))
    assertContains(
        response, '<td data-label="Run">8 · transmits final model 7</td>', html=True
    )
