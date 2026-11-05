"""Views of the startup's training runs: who may, what the Final models page shows."""

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
from django.contrib.messages import get_messages
from django.test import Client
from django.urls import reverse
from pytest_django import DjangoAssertNumQueries
from pytest_django.asserts import assertContains, assertRedirects
from pytest_django.fixtures import Settings

from iron_deficiency.final_models import keep_final_model
from iron_deficiency.task import Net
from tests.conftest import make_data_scientist, make_laboratory_director

pytestmark = pytest.mark.django_db


@pytest.fixture
def final_models_dir(tmp_path: Path, settings: Settings) -> Path:
    directory = tmp_path / "final-models"
    settings.FINAL_MODELS_DIR = directory
    keep_final_model(
        directory,
        run_id=7,
        state_dict=Net().state_dict(),
        threshold=0.4,
        federated={"eval_auroc": 0.861},
        stored_at=datetime(2026, 10, 30, 9, 0, tzinfo=UTC),
    )
    return directory


def test_final_models_page(
    client: Client,
    final_models_dir: Path,
    django_assert_num_queries: DjangoAssertNumQueries,
) -> None:
    client.force_login(make_data_scientist("Data One").user)
    # Session, user with role.
    with django_assert_num_queries(2):
        response = client.get(reverse("training:final_models"))
    assertContains(
        response,
        "<tr><td>30 Oct 2026, 10:00</td><td>7</td><td>0.4</td><td>0.86</td></tr>",
        html=True,
    )


def test_a_laboratory_director_is_sent_to_their_own_page(client: Client) -> None:
    client.force_login(make_laboratory_director("Director One").user)
    response = client.get(reverse("training:final_models"))
    assertRedirects(response, reverse("deployment:models"))


def answering(monkeypatch: pytest.MonkeyPatch, answer: dict[str, object]) -> None:
    """`flwr run` answering as Flower's JSON output does."""

    def run(command: list[str], **kwargs: object) -> "subprocess.CompletedProcess[str]":
        return subprocess.CompletedProcess(command, 0, json.dumps(answer), "")

    monkeypatch.setattr(subprocess, "run", run)


@pytest.fixture
def data_scientist(client: Client) -> None:
    client.force_login(make_data_scientist("Data One").user)


@pytest.mark.usefixtures("data_scientist")
def test_submitting_a_run_redirects_to_the_final_models(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    answering(monkeypatch, {"success": True, "run-id": "7"})
    response = client.post(reverse("training:final_models"), {"threshold": "0.4"})
    assertRedirects(response, reverse("training:final_models"))
    assert [str(message) for message in get_messages(response.wsgi_request)] == [
        "Training run 7 submitted. Its final model appears here when the run finishes."
    ]


@pytest.mark.usefixtures("data_scientist")
@pytest.mark.parametrize(
    ("threshold", "field", "code"),
    [
        ("0", "threshold", "threshold_not_above_zero"),
        ("1", "threshold", "threshold_not_below_one"),
        ("", "threshold", "required"),
    ],
)
def test_a_refused_threshold_stays_on_the_page(
    client: Client,
    monkeypatch: pytest.MonkeyPatch,
    threshold: str,
    field: str,
    code: str,
) -> None:
    answering(monkeypatch, {"success": True, "run-id": "7"})
    response = client.post(reverse("training:final_models"), {"threshold": threshold})
    assert response.status_code == 200
    assert [
        error.code for error in response.context["form"].errors.as_data()[field]
    ] == [code]


@pytest.mark.usefixtures("data_scientist")
def test_a_refused_run_says_why(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    answering(monkeypatch, {"success": False, "error-message": "unavailable"})
    response = client.post(reverse("training:final_models"), {"threshold": "0.5"})
    assert response.status_code == 200
    errors = response.context["form"].errors.as_data()["__all__"]
    assert [error.code for error in errors] == ["superlink_refused"]
    assertContains(response, "The SuperLink refused the run: unavailable")


def test_a_deployment_tells_the_server_app_its_demo_folder(
    settings: Settings, tmp_path: Path
) -> None:
    from web.training.runs import run_configuration

    settings.STARTUP_DIR = tmp_path / "startup"
    assert run_configuration(0.4) == f"demo-dir='{tmp_path}' screening-threshold=0.4"
