"""Views of deploying models: who may, what the Models page shows."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from django.test import Client
from django.urls import reverse
from pytest_django import DjangoAssertNumQueries
from pytest_django.asserts import assertContains
from pytest_django.fixtures import Settings

from tests.conftest import (
    make_laboratory_director,
    make_laboratory_staff_member,
    write_final_model,
)
from web.deployment.models import Deployment, LaboratoryDirector

pytestmark = pytest.mark.django_db
VALIDATION = {
    0.4: {
        "true_positives": 9,
        "false_negatives": 1,
        "false_positives": 12,
        "true_negatives": 30,
    },
    0.5: {
        "true_positives": 7,
        "false_negatives": 3,
        "false_positives": 5,
        "true_negatives": 37,
    },
}


@pytest.fixture
def screening_models_dir(tmp_path: Path, settings: Settings) -> Path:
    directory = tmp_path / "screening-models"
    directory.mkdir()
    settings.SCREENING_MODELS_DIR = directory
    stored_at = datetime(2026, 10, 30, 9, 0, tzinfo=UTC)
    write_final_model(directory, "run-1", VALIDATION, stored_at)
    (directory / "run-2.pt").write_bytes(b"not a model")
    return directory


@pytest.fixture
def director(client: Client) -> LaboratoryDirector:
    director = make_laboratory_director("Director One")
    client.force_login(director.user)
    return director


def test_models_page(
    client: Client,
    director: LaboratoryDirector,
    screening_models_dir: Path,
    django_assert_num_queries: DjangoAssertNumQueries,
) -> None:
    # Session, user with role, deployed model, deployment history.
    with django_assert_num_queries(4):
        response = client.get(reverse("deployment:models"))
    assertContains(
        response,
        '<h2>Screening model of <span class="no-wrap">30 Oct 2026, 10:00</span></h2>',
        html=True,
    )
    assertContains(
        response,
        'aria-label="Deploy Screening model of 30 Oct 2026, 10:00 at the chosen'
        ' threshold"',
    )
    # One row per threshold, each with its radio button and four measures.
    for threshold, cells in (
        ("0.4", ("9 of 10 (90%)", "30 of 42 (71%)", "9 of 21 (43%)", "30 of 31 (97%)")),
        ("0.5", ("7 of 10 (70%)", "37 of 42 (88%)", "7 of 12 (58%)", "37 of 40 (92%)")),
    ):
        assertContains(
            response, f'name="threshold" value="{threshold}" required', count=1
        )
        for cell in cells:
            assertContains(response, f"<td>{cell}</td>", html=True)
    for term, value in (("AUROC here", "0.84"), ("AUROC across hospitals", "0.87")):
        assertContains(response, f"<dt>{term}</dt><dd>{value}</dd>", html=True)
    assertContains(response, "Cannot be deployed: not a readable model file")
    assertContains(response, "No screening model is deployed")


def test_deploying_redirects_with_a_message(
    client: Client, director: LaboratoryDirector, screening_models_dir: Path
) -> None:
    url = reverse("deployment:deploy", kwargs={"run_id": "run-1"})
    response = client.post(url, {"threshold": "0.4"}, follow=True)
    assert response.redirect_chain == [(reverse("deployment:models"), 302)]
    assertContains(
        response, "Screening model of 30 Oct 2026, 10:00 deployed at threshold 0.40."
    )
    screening_model = Deployment.objects.get().screening_model
    assert (screening_model.run_id, screening_model.threshold) == ("run-1", 0.4)
    # The deployed threshold is the one chosen when the page shows again.
    assertContains(response, "Deployed at threshold 0.40")
    assertContains(response, 'value="0.4" required checked')


@pytest.mark.parametrize("posted", [{}, {"threshold": "high"}])
def test_deploying_without_a_threshold_says_so(
    client: Client,
    director: LaboratoryDirector,
    screening_models_dir: Path,
    posted: dict[str, str],
) -> None:
    url = reverse("deployment:deploy", kwargs={"run_id": "run-1"})
    response = client.post(url, posted, follow=True)
    assert response.redirect_chain == [(reverse("deployment:models"), 302)]
    assertContains(response, "Choose a threshold to deploy at.")
    assert not Deployment.objects.exists()


def test_a_refused_deployment_says_why(
    client: Client, director: LaboratoryDirector, screening_models_dir: Path
) -> None:
    url = reverse("deployment:deploy", kwargs={"run_id": "run-2"})
    response = client.post(url, {"threshold": "0.5"}, follow=True)
    assertContains(response, "not a readable model file")
    assert not Deployment.objects.exists()


def test_deploy_is_post_only(
    client: Client, director: LaboratoryDirector, screening_models_dir: Path
) -> None:
    url = reverse("deployment:deploy", kwargs={"run_id": "run-1"})
    assert client.get(url).status_code == 405


def test_laboratory_staff_are_sent_to_their_start_page(
    client: Client, screening_models_dir: Path
) -> None:
    client.force_login(make_laboratory_staff_member("Lab One").user)
    response = client.get(reverse("deployment:models"), follow=True)
    assert response.redirect_chain == [(reverse("lab:to_analyse"), 302)]
    assertContains(response, "That page is for laboratory directors.")


def test_without_a_screening_models_folder(
    client: Client, director: LaboratoryDirector, settings: Settings
) -> None:
    settings.SCREENING_MODELS_DIR = None
    assertContains(client.get(reverse("deployment:models")), "No models have arrived.")


def status(settings: Settings) -> str:
    from io import StringIO

    from django.core.management import call_command

    out = StringIO()
    call_command("screening_status", stdout=out)
    return out.getvalue().strip()


def test_screening_status_without_models(settings: Settings, tmp_path: Path) -> None:
    settings.SCREENING_MODELS_DIR = tmp_path / "screening-models"
    assert status(settings) == "no screening model yet"


def test_screening_status_before_and_after_deploying(
    client: Client,
    director: LaboratoryDirector,
    screening_models_dir: Path,
    settings: Settings,
) -> None:
    assert status(settings) == "2 screening models, none deployed"
    client.post(
        reverse("deployment:deploy", kwargs={"run_id": "run-1"}), {"threshold": "0.5"}
    )
    assert (
        status(settings) == "Screening model of 30 Oct 2026, 10:00 deployed (2 in all)"
    )
