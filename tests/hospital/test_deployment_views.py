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
    write_screening_model,
)
from web.hospital.deployment.models import Deployment, TargetSensitivity
from web.shared.accounts.models import User

pytestmark = pytest.mark.django_db
VALIDATION = {
    0.2: {
        "true_positives": 10,
        "false_negatives": 0,
        "false_positives": 20,
        "true_negatives": 22,
    },
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
    write_screening_model(directory, "1", VALIDATION, stored_at)
    (directory / "2.pt").write_bytes(b"not a model")
    return directory


@pytest.fixture
def director(client: Client) -> User:
    director = make_laboratory_director("Director One")
    client.force_login(director)
    return director


def set_target(client: Client, percent: str) -> None:
    client.post(reverse("deployment:screening_models"), {"percent": percent})


def test_models_page(
    client: Client,
    director: User,
    screening_models_dir: Path,
    django_assert_num_queries: DjangoAssertNumQueries,
) -> None:
    # Session, user with role, deployed screening model, target sensitivity,
    # target sensitivities and deployments for the history.
    with django_assert_num_queries(6):
        response = client.get(reverse("deployment:screening_models"))
    assertContains(
        response,
        '<h3>Screening model of <span class="no-wrap">30 Oct 2026, 10:00</span></h3>',
        html=True,
    )
    # Without a target sensitivity nothing can be deployed, so nothing offers to.
    assertContains(response, "No target sensitivity is set")
    assertNotContains(response, "Deploy Screening model")
    for percent in ("80", "85", "90", "95", "100"):
        assertContains(response, f'name="percent" value="{percent}"', count=1)
    assertContains(
        response, "Set a target sensitivity to see what this screening model costs"
    )
    assertContains(
        response,
        "<p><strong>Performs here as claimed across hospitals</strong>: AUROC 0.84"
        ' here <span class="no-wrap">(95% CI 0.68–1.00)</span>, 0.87 across'
        " hospitals.</p>",
        html=True,
    )
    # The unreadable file is no screening model: it is not listed.
    assertContains(response, "<small>run 1</small>", count=1)
    assertNotContains(response, "<small>run 2</small>")
    assertContains(response, "No screening model is deployed")


def test_a_screening_model_at_the_target_sensitivity(
    client: Client, director: User, screening_models_dir: Path
) -> None:
    set_target(client, "90")
    response = client.get(reverse("deployment:screening_models"))
    # 90% resolves to 0.4: 0.5 finds only 7 of 10.
    assertContains(
        response,
        "At 90%, it suggests ferritin for 12 of 42 past patients without iron"
        " deficiency (threshold 0.40).",
    )
    for term, measure in (
        ("Sensitivity", '9 of 10 (90%; <span class="no-wrap">95% CI 60–98%</span>)'),
        ("Specificity", '30 of 42 (71%; <span class="no-wrap">95% CI 56–83%</span>)'),
        (
            "Positive predictive value",
            '9 of 21 (43%; <span class="no-wrap">95% CI 24–63%</span>)',
        ),
        (
            "Negative predictive value",
            '30 of 31 (97%; <span class="no-wrap">95% CI 84–99%</span>)',
        ),
    ):
        assertContains(response, f"<dt>{term}</dt>", count=1, html=True)
        assertContains(response, measure, count=1)
    assertContains(
        response,
        "Iron deficient: ferritin below 15&nbsp;ng/mL, or below 70&nbsp;ng/mL with"
        " inflammation (CRP above 5&nbsp;mg/L)",
    )
    # One row per threshold is gone: the page shows the target's only.
    assertNotContains(response, "7 of 10")


def test_setting_the_target_sensitivity_redirects_with_a_message(
    client: Client, director: User, screening_models_dir: Path
) -> None:
    response = client.post(
        reverse("deployment:screening_models"), {"percent": "90"}, follow=True
    )
    assert response.redirect_chain == [(reverse("deployment:screening_models"), 302)]
    assertContains(response, "Target sensitivity set to 90%.")
    assertContains(response, "Now <strong>90%</strong>, set by director-one")
    assertContains(
        response, 'name="percent" value="90" required id="id_percent_2" checked'
    )
    assertContains(
        response,
        'aria-label="Deploy Screening model of 30 Oct 2026, 10:00 at 90%"',
    )
    assert TargetSensitivity.objects.get().set_by == director


@pytest.mark.parametrize("posted", [{}, {"percent": "75"}, {"percent": "high"}])
def test_setting_no_target_sensitivity_says_so_beside_the_field(
    client: Client,
    director: User,
    screening_models_dir: Path,
    posted: dict[str, str],
) -> None:
    response = client.post(reverse("deployment:screening_models"), posted)
    assert response.status_code == 200
    assertContains(
        response,
        '<a href="#id_percent_0">Target sensitivity: Choose a target sensitivity.</a>',
        html=True,
    )
    assert not TargetSensitivity.objects.exists()


def test_deploying_redirects_with_a_message(
    client: Client, director: User, screening_models_dir: Path
) -> None:
    set_target(client, "90")
    url = reverse("deployment:deploy", kwargs={"run_id": "1"})
    response = client.post(url, follow=True)
    assert response.redirect_chain == [(reverse("deployment:screening_models"), 302)]
    assertContains(
        response,
        "Screening model of 30 Oct 2026, 10:00 deployed at threshold 0.40 (target 90%).",
    )
    deployment = Deployment.objects.get()
    screening_model = deployment.deployed_screening_model
    assert (screening_model.run_id, screening_model.threshold) == ("1", 0.4)
    assert deployment.deployed_by == director
    assertContains(response, "Deployed at threshold 0.40")
    # The history names both decisions and who made them.
    assertContains(response, "<td>Target sensitivity set to 90%</td>", html=True)
    assertContains(
        response,
        "<td>Screening model of 30 Oct 2026, 10:00 deployed at threshold 0.40"
        " (target 90%)</td>",
        html=True,
    )
    assertContains(response, "<td>director-one</td>", count=2, html=True)


def test_deploying_before_a_target_sensitivity_says_so(
    client: Client, director: User, screening_models_dir: Path
) -> None:
    url = reverse("deployment:deploy", kwargs={"run_id": "1"})
    response = client.post(url, follow=True)
    assertContains(
        response, "Set a target sensitivity before deploying a screening model."
    )
    assert not Deployment.objects.exists()


def test_a_refused_deployment_says_why(
    client: Client, director: User, screening_models_dir: Path
) -> None:
    set_target(client, "90")
    url = reverse("deployment:deploy", kwargs={"run_id": "2"})
    response = client.post(url, follow=True)
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
    client: Client, director: User, settings: Settings, tmp_path: Path
) -> None:
    settings.SCREENING_MODELS_DIR = tmp_path / "absent"
    assertContains(
        client.get(reverse("deployment:screening_models")),
        "No screening model fetched yet.",
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
    set_target(client, "90")
    client.post(reverse("deployment:deploy", kwargs={"run_id": "1"}))
    assert (
        status(settings) == "Screening model of 30 Oct 2026, 10:00 deployed (1 in all)"
    )
