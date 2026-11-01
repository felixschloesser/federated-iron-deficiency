"""Views of deploying models: who may, what the Models page shows."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from django.test import Client
from django.urls import reverse
from pytest_django import DjangoAssertNumQueries
from pytest_django.asserts import assertContains
from pytest_django.fixtures import Settings

from tests.conftest import make_laboratory_director, make_laboratory_staff_member
from tests.test_deployment import write_final_model
from web.deployment.models import Deployment, LaboratoryDirector

pytestmark = pytest.mark.django_db
VALIDATION = {
    "true_positives": 7,
    "false_negatives": 3,
    "false_positives": 5,
    "true_negatives": 37,
    "auroc": 0.84,
}


@pytest.fixture
def final_models_dir(tmp_path: Path, settings: Settings) -> Path:
    directory = tmp_path / "final-models"
    directory.mkdir()
    settings.FINAL_MODELS_DIR = directory
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
    final_models_dir: Path,
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
        response, 'aria-label="Deploy Screening model of 30 Oct 2026, 10:00"'
    )
    for term, value in (
        ("Sensitivity", "7 of 10 iron-deficient women (70%)"),
        ("Specificity", "37 of 42 women without iron deficiency (88%)"),
        ("Positive predictive value", "7 of 12 ferritin suggestions (58%)"),
        ("Negative predictive value", "37 of 40 women without a suggestion (92%)"),
        ("AUROC here", "0.84"),
        ("AUROC across hospitals", "0.87"),
        ("Threshold", "0.5"),
    ):
        assertContains(response, f"<dt>{term}</dt><dd>{value}</dd>", html=True)
    assertContains(response, "Cannot be deployed: not a readable model file")
    assertContains(response, "No screening model is deployed")


def test_deploying_redirects_with_a_message(
    client: Client, director: LaboratoryDirector, final_models_dir: Path
) -> None:
    url = reverse("deployment:deploy", kwargs={"run_id": "run-1"})
    response = client.post(url, follow=True)
    assert response.redirect_chain == [(reverse("deployment:models"), 302)]
    assertContains(response, "Screening model of 30 Oct 2026, 10:00 deployed.")
    assert Deployment.objects.get().screening_model.run_id == "run-1"


def test_a_refused_deployment_says_why(
    client: Client, director: LaboratoryDirector, final_models_dir: Path
) -> None:
    url = reverse("deployment:deploy", kwargs={"run_id": "run-2"})
    assertContains(client.post(url, follow=True), "not a readable model file")
    assert not Deployment.objects.exists()


def test_deploy_is_post_only(
    client: Client, director: LaboratoryDirector, final_models_dir: Path
) -> None:
    url = reverse("deployment:deploy", kwargs={"run_id": "run-1"})
    assert client.get(url).status_code == 405


def test_laboratory_staff_are_sent_to_their_start_page(
    client: Client, final_models_dir: Path
) -> None:
    client.force_login(make_laboratory_staff_member("Lab One").user)
    response = client.get(reverse("deployment:models"), follow=True)
    assert response.redirect_chain == [(reverse("lab:to_analyse"), 302)]
    assertContains(response, "That page is for laboratory directors.")


def test_without_a_final_models_folder(
    client: Client, director: LaboratoryDirector, settings: Settings
) -> None:
    settings.FINAL_MODELS_DIR = None
    assertContains(client.get(reverse("deployment:models")), "No models have arrived.")
