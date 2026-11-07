"""Views of providing the training cohort: who may, what the page shows, where
each action leads."""

from pathlib import Path

import pytest
from django.test import Client
from django.urls import reverse
from pytest_django import DjangoAssertNumQueries
from pytest_django.asserts import assertContains
from pytest_django.fixtures import Settings

from hospital.cohort.models import TrainingCohort
from shared.accounts.models import User
from shared.accounts.roles import Role
from tests.hospital.conftest import (
    make_lab_records,
    make_laboratory_director,
    make_laboratory_staff_member,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def cohort_dir(tmp_path: Path, settings: Settings) -> Path:
    directory = tmp_path / "cohort"
    settings.TRAINING_COHORT_DIR = directory
    return directory


@pytest.fixture
def director(client: Client) -> User:
    director = make_laboratory_director("Director One")
    client.force_login(director)
    return director


def test_the_page_before_providing(
    client: Client,
    director: User,
    cohort_dir: Path,
    django_assert_num_queries: DjangoAssertNumQueries,
) -> None:
    make_lab_records(120, iron_deficient=20)
    # Session, user with role, the provided cohort, the summary, the decisions.
    with django_assert_num_queries(5):
        response = client.get(reverse("cohort:training_cohort"))
    assert response.status_code == 200
    assert response.context["provided"] is None
    assert (
        response.context["summary"].past_patients,
        response.context["summary"].iron_deficient,
    ) == (120, 20)
    assertContains(response, reverse("cohort:provide"))
    assert reverse("cohort:withdraw") not in response.content.decode()


def test_the_page_once_provided_offers_withdrawing(
    client: Client, director: User, cohort_dir: Path
) -> None:
    make_lab_records(120, iron_deficient=20)
    client.post(reverse("cohort:provide"))
    response = client.get(reverse("cohort:training_cohort"))
    provided = response.context["provided"]
    assert provided is not None
    assertContains(response, reverse("cohort:withdraw"))
    assertContains(response, provided.sha256)


def test_providing_redirects_with_a_message(
    client: Client, director: User, cohort_dir: Path
) -> None:
    make_lab_records(120, iron_deficient=20)
    response = client.post(reverse("cohort:provide"), follow=True)
    assert response.redirect_chain == [(reverse("cohort:training_cohort"), 302)]
    assertContains(response, "Training cohort provided: 120 past patients.")
    assert TrainingCohort.objects.provided() is not None


def test_a_refused_provision_says_why(
    client: Client, director: User, cohort_dir: Path
) -> None:
    make_lab_records(99, iron_deficient=20)
    response = client.post(reverse("cohort:provide"), follow=True)
    assert response.redirect_chain == [(reverse("cohort:training_cohort"), 302)]
    assertContains(response, "at least 100 eligible past patients")
    assert TrainingCohort.objects.provided() is None


def test_withdrawing_redirects_with_a_message(
    client: Client, director: User, cohort_dir: Path
) -> None:
    make_lab_records(120, iron_deficient=20)
    client.post(reverse("cohort:provide"))
    response = client.post(reverse("cohort:withdraw"), follow=True)
    assert response.redirect_chain == [(reverse("cohort:training_cohort"), 302)]
    assertContains(response, "Training cohort withdrawn.")
    assert TrainingCohort.objects.provided() is None


@pytest.mark.parametrize("name", ["cohort:provide", "cohort:withdraw"])
def test_actions_are_post_only(
    client: Client, director: User, cohort_dir: Path, name: str
) -> None:
    assert client.get(reverse(name)).status_code == 405


def test_laboratory_staff_are_sent_to_their_start_page(
    client: Client, cohort_dir: Path
) -> None:
    client.force_login(make_laboratory_staff_member("Lab One"))
    response = client.get(reverse("cohort:training_cohort"), follow=True)
    assert response.redirect_chain == [(reverse("lab:test_requests"), 302)]


def test_the_laboratory_director_finds_the_page() -> None:
    assert {
        "url": reverse("cohort:training_cohort"),
        "label": "Training cohort",
    } in Role.LABORATORY_DIRECTOR.nav_links()
