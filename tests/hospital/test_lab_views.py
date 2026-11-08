"""Views of the laboratory side, and moving between the two roles' pages."""

from datetime import UTC, datetime

import pytest
from django.test import Client
from django.urls import reverse
from pytest_django import DjangoAssertNumQueries
from pytest_django.asserts import assertContains, assertNotContains

from tests.hospital.conftest import (
    make_laboratory_director,
    make_laboratory_staff_member,
    make_tube,
    receive_lab_order,
)
from web.hospital.lab.models import TestRequest
from web.shared.accounts.models import User
from web.shared.vocabulary import RegisteredSex
from web.shared.vocabulary import Test as OrderedTest

ORDERED = datetime(2026, 10, 29, 9, 0, tzinfo=UTC)

pytestmark = pytest.mark.django_db


@pytest.fixture
def staff_member() -> User:
    return make_laboratory_staff_member("Lab One")


@pytest.fixture
def test_request() -> TestRequest:
    """A ferritin ordered by a general practitioner, as the lab received it (DF23)."""
    receive_lab_order(f"{make_tube().seqn}-1", OrderedTest.FERRITIN, ORDERED)
    return TestRequest.objects.select_related("sample").get()


def logged_in(client: Client, staff_member: User) -> Client:
    client.force_login(staff_member)
    return client


def analyse_url(test_request: TestRequest) -> str:
    return reverse("lab:analyse", kwargs={"pk": test_request.pk})


@pytest.mark.parametrize("page", ["lab:test_requests", "lab:analysed"])
def test_lab_index_queries(
    client: Client,
    staff_member: User,
    test_request: TestRequest,
    django_assert_num_queries: DjangoAssertNumQueries,
    page: str,
) -> None:
    logged_in(client, staff_member)
    # Session, user with role, lab orders with their samples.
    with django_assert_num_queries(3):
        assert client.get(reverse(page)).status_code == 200


def test_lab_pages_never_show_a_patient_name(
    client: Client, staff_member: User, test_request: TestRequest
) -> None:
    logged_in(client, staff_member)
    assertNotContains(client.get(reverse("lab:test_requests")), "Test Patient 1")
    client.post(analyse_url(test_request))
    assertNotContains(client.get(reverse("lab:analysed")), "Test Patient 1")


def test_navigation_links_to_both_lab_pages(client: Client, staff_member: User) -> None:
    response = logged_in(client, staff_member).get(reverse("lab:test_requests"))
    assertContains(response, f'href="{reverse("lab:test_requests")}"')
    assertContains(response, f'href="{reverse("lab:analysed")}"')


def test_running_the_analyser(
    client: Client, staff_member: User, test_request: TestRequest
) -> None:
    response = logged_in(client, staff_member).post(analyse_url(test_request))
    assert response["Location"] == reverse("lab:test_requests")
    assertContains(
        client.get(response["Location"]),
        f"Sample {test_request.sample.sample_id}: ferritin analysed, lab report released.",
    )
    test_request.refresh_from_db()
    assert test_request.analysed_at is not None


def test_actions_are_post_only(
    client: Client, staff_member: User, test_request: TestRequest
) -> None:
    logged_in(client, staff_member)
    assert client.get(analyse_url(test_request)).status_code == 405


def test_laboratory_director_is_sent_to_their_start_page(client: Client) -> None:
    client.force_login(make_laboratory_director("Director"))
    response = client.get(reverse("lab:test_requests"), follow=True)
    assert response.redirect_chain == [(reverse("deployment:screening_models"), 302)]
    assertContains(response, "That page is for laboratory staff.")


def test_laboratory_director_cannot_run_the_analyser(
    client: Client, test_request: TestRequest
) -> None:
    client.force_login(make_laboratory_director("Director"))
    client.post(analyse_url(test_request))
    test_request.refresh_from_db()
    assert test_request.analysed_at is None


def cbc_lab_order(sex: RegisteredSex) -> TestRequest:
    """A CBC for a screened indication, aged 32, as the lab received it (DF23)."""
    receive_lab_order(f"{make_tube().seqn}-1", OrderedTest.CBC, ORDERED, sex=sex)
    return TestRequest.objects.select_related("sample").get()


def test_a_cbc_not_screened_for_a_model_problem_warns(
    client: Client, staff_member: User
) -> None:
    test_request = cbc_lab_order(RegisteredSex.FEMALE)
    response = logged_in(client, staff_member).post(
        analyse_url(test_request), follow=True
    )
    assertContains(response, 'data-level="warning"')
    assertContains(
        response,
        f"Sample {test_request.sample.sample_id}: CBC analysed, lab report released"
        " without screening. Tell the laboratory director.",
    )


def test_a_cbc_not_screened_for_eligibility_does_not_warn(
    client: Client, staff_member: User
) -> None:
    test_request = cbc_lab_order(RegisteredSex.MALE)
    response = logged_in(client, staff_member).post(
        analyse_url(test_request), follow=True
    )
    assertNotContains(response, 'data-level="warning"')
    assertContains(
        response,
        f"Sample {test_request.sample.sample_id}: CBC analysed, lab report released.",
    )


def test_run_analyser_names_its_sample_for_assistive_technology(
    client: Client, staff_member: User, test_request: TestRequest
) -> None:
    response = logged_in(client, staff_member).get(reverse("lab:test_requests"))
    sample_id = test_request.sample.sample_id
    assertContains(response, f'aria-label="Run analyser for sample {sample_id}"')
    assertContains(response, f'<span class="sample-id">{sample_id}</span>')


def test_to_analyse_shows_only_what_running_the_analyser_needs(
    client: Client, staff_member: User, test_request: TestRequest
) -> None:
    response = logged_in(client, staff_member).get(reverse("lab:test_requests"))
    for heading in ("Sample ID", "Test", "Ordered"):
        assertContains(response, f'<th scope="col">{heading}</th>')
    for heading in (
        "General practitioner",
        "Clinical indication",
        "Registered sex",
        "Age",
    ):
        assertNotContains(response, f'<th scope="col">{heading}</th>')
    assertNotContains(response, "· stored sample")


def test_to_analyse_marks_a_stored_sample(
    client: Client, staff_member: User, test_request: TestRequest
) -> None:
    logged_in(client, staff_member).post(analyse_url(test_request))
    # The sample's other test reaching the lab after its ferritin was analysed:
    # here the CBC whose lab report suggested ferritin at the practice.
    receive_lab_order(test_request.sample.sample_id, OrderedTest.CBC, ORDERED)
    response = client.get(reverse("lab:test_requests"))
    sample_id = test_request.sample.sample_id
    assertContains(response, f"{sample_id}</span> · stored sample")


def test_analysed_names_no_general_practitioner(
    client: Client, staff_member: User, test_request: TestRequest
) -> None:
    test_request.run_analyser(directory=None, now=test_request.ordered_at)
    response = logged_in(client, staff_member).get(reverse("lab:analysed"))
    assertNotContains(response, '<th scope="col">General practitioner</th>')


def test_an_action_button_is_plain_so_pico_adds_no_form_margin(
    client: Client, staff_member: User, test_request: TestRequest
) -> None:
    # Pico's [type=submit] adds a bottom margin meant for a form's last button;
    # an action button submits by default and sits in a table cell or a row.
    response = logged_in(client, staff_member).get(reverse("lab:test_requests"))
    sample_id = test_request.sample.sample_id
    assertContains(
        response,
        f'<button aria-label="Run analyser for sample {sample_id}">Run analyser</button>',
    )


def test_the_header_marks_the_current_page(client: Client, staff_member: User) -> None:
    response = logged_in(client, staff_member).get(reverse("lab:analysed"))
    assertContains(
        response,
        f'<a href="{reverse("lab:analysed")}" aria-current="page">Analysed</a>',
        html=True,
    )
    assertContains(
        response, f'<a href="{reverse("lab:test_requests")}">To analyse</a>', html=True
    )
