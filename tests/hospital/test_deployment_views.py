"""Views of deploying models: who may, what the Models page shows."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from django.test import Client
from django.urls import reverse
from pytest_django import DjangoAssertNumQueries
from pytest_django.asserts import assertContains, assertNotContains
from pytest_django.fixtures import Settings

from tests.hospital.conftest import (
    make_laboratory_director,
    make_laboratory_staff_member,
    write_final_model,
)
from web.hospital.deployment.models import Deployment
from web.shared.accounts.models import User

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
    write_final_model(directory, "1", VALIDATION, stored_at)
    (directory / "2.pt").write_bytes(b"not a model")
    return directory


@pytest.fixture
def director(client: Client) -> User:
    director = make_laboratory_director("Director One")
    client.force_login(director)
    return director


def test_models_page(
    client: Client,
    director: User,
    screening_models_dir: Path,
    django_assert_num_queries: DjangoAssertNumQueries,
) -> None:
    # Session, user with role, deployed model, deployment history.
    with django_assert_num_queries(4):
        response = client.get(reverse("deployment:screening_models"))
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
        (
            "0.4",
            (
                '9 of 10 (90%; <span class="no-wrap">95% CI 60–98%</span>)',
                '30 of 42 (71%; <span class="no-wrap">95% CI 56–83%</span>)',
                '9 of 21 (43%; <span class="no-wrap">95% CI 24–63%</span>)',
                '30 of 31 (97%; <span class="no-wrap">95% CI 84–99%</span>)',
            ),
        ),
        (
            "0.5",
            (
                '7 of 10 (70%; <span class="no-wrap">95% CI 40–89%</span>)',
                '37 of 42 (88%; <span class="no-wrap">95% CI 75–95%</span>)',
                '7 of 12 (58%; <span class="no-wrap">95% CI 32–81%</span>)',
                '37 of 40 (92%; <span class="no-wrap">95% CI 80–97%</span>)',
            ),
        ),
    ):
        assertContains(
            response, f'name="threshold" value="{threshold}" required', count=1
        )
        for label, cell in zip(
            (
                "Sensitivity",
                "Specificity",
                "Positive predictive value",
                "Negative predictive value",
            ),
            cells,
            strict=True,
        ):
            assertContains(response, f'<td data-label="{label}">{cell}</td>', html=True)
    assertContains(
        response,
        '<dt>AUROC here</dt><dd>0.84 <span class="no-wrap">(95% CI 0.68–1.00)</span></dd>',
        html=True,
    )
    assertContains(response, "<dt>AUROC across hospitals</dt><dd>0.87</dd>", html=True)
    # The unreadable file is no screening model: it is not listed.
    assertContains(response, "<small>run 1</small>", count=1)
    assertNotContains(response, "<small>run 2</small>")
    assertContains(response, "No screening model is deployed")


def test_deploying_redirects_with_a_message(
    client: Client, director: User, screening_models_dir: Path
) -> None:
    url = reverse("deployment:deploy", kwargs={"run_id": "1"})
    response = client.post(url, {"threshold": "0.4"}, follow=True)
    assert response.redirect_chain == [(reverse("deployment:screening_models"), 302)]
    assertContains(
        response, "Screening model of 30 Oct 2026, 10:00 deployed at threshold 0.40."
    )
    screening_model = Deployment.objects.get().screening_model
    assert (screening_model.run_id, screening_model.threshold) == ("1", 0.4)
    # The deployed threshold is the one chosen when the page shows again.
    assertContains(response, "Deployed at threshold 0.40")
    assertContains(response, 'value="0.4" required checked')


@pytest.mark.parametrize("posted", [{}, {"threshold": "high"}])
def test_deploying_without_a_threshold_says_so(
    client: Client,
    director: User,
    screening_models_dir: Path,
    posted: dict[str, str],
) -> None:
    url = reverse("deployment:deploy", kwargs={"run_id": "1"})
    response = client.post(url, posted, follow=True)
    assert response.redirect_chain == [(reverse("deployment:screening_models"), 302)]
    assertContains(response, "Choose a threshold to deploy at.")
    assert not Deployment.objects.exists()


def test_a_refused_deployment_says_why(
    client: Client, director: User, screening_models_dir: Path
) -> None:
    url = reverse("deployment:deploy", kwargs={"run_id": "2"})
    response = client.post(url, {"threshold": "0.5"}, follow=True)
    assertContains(response, "There is no readable model of run 2.")
    assert not Deployment.objects.exists()


def test_deploy_is_post_only(
    client: Client, director: User, screening_models_dir: Path
) -> None:
    url = reverse("deployment:deploy", kwargs={"run_id": "1"})
    assert client.get(url).status_code == 405


def test_laboratory_staff_are_sent_to_their_start_page(
    client: Client, screening_models_dir: Path
) -> None:
    client.force_login(make_laboratory_staff_member("Lab One"))
    response = client.get(reverse("deployment:screening_models"), follow=True)
    assert response.redirect_chain == [(reverse("lab:test_requests"), 302)]
    assertContains(response, "That page is for laboratory directors.")


def test_a_file_not_named_after_a_run_is_no_screening_model(
    screening_models_dir: Path,
) -> None:
    from web.hospital.deployment.model_files import screening_models

    (screening_models_dir / "1.pt").rename(screening_models_dir / "run123.pt")
    (screening_models_dir / "2.pt").unlink()
    assert screening_models(screening_models_dir) == []


def test_without_a_screening_models_folder(
    client: Client, director: User, settings: Settings
) -> None:
    settings.SCREENING_MODELS_DIR = None
    assertContains(
        client.get(reverse("deployment:screening_models")),
        "No final model fetched yet.",
    )


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
    director: User,
    screening_models_dir: Path,
    settings: Settings,
) -> None:
    # The unreadable "2.pt" is no screening model.
    assert status(settings) == "1 screening model, none deployed"
    client.post(
        reverse("deployment:deploy", kwargs={"run_id": "1"}), {"threshold": "0.5"}
    )
    assert (
        status(settings) == "Screening model of 30 Oct 2026, 10:00 deployed (1 in all)"
    )
