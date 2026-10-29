"""Views of the general practitioner side: status, redirects, form error codes, query counts."""

import pytest
from django.template.loader import render_to_string
from django.test import Client
from django.urls import reverse
from pytest_django import DjangoAssertNumQueries
from pytest_django.asserts import assertContains

from tests.conftest import make_general_practitioner, make_patient
from web.accounts.models import User
from web.practice.models import GeneralPractitioner, Order, Patient, RegisteredSex

pytestmark = pytest.mark.django_db


@pytest.fixture
def general_practitioner() -> GeneralPractitioner:
    return make_general_practitioner("Dr. Demo A")


@pytest.fixture
def patient(general_practitioner: GeneralPractitioner) -> Patient:
    return make_patient(
        general_practitioner, "Test Patient 1", RegisteredSex.FEMALE, 32
    )


def logged_in(client: Client, general_practitioner: GeneralPractitioner) -> Client:
    client.force_login(general_practitioner.user)
    return client


def test_anonymous_is_sent_to_login(client: Client) -> None:
    response = client.get(reverse("practice:index"))
    assert response.status_code == 302
    assert response["Location"].startswith(reverse("login"))


def test_user_who_is_not_a_general_practitioner_is_refused(client: Client) -> None:
    client.force_login(User.objects.create_user(username="lab"))
    assert client.get(reverse("practice:index")).status_code == 403
    assert client.get(reverse("practice:new_order")).status_code == 403


def test_index_queries(
    client: Client,
    general_practitioner: GeneralPractitioner,
    patient: Patient,
    django_assert_num_queries: DjangoAssertNumQueries,
) -> None:
    logged_in(client, general_practitioner)
    form = {"patient": patient.pk, "test": "ferritin", "indication": ""}
    for _ in range(4):
        client.post(reverse("practice:new_order"), form)
    # Session, user, GeneralPractitioner, and the orders with their patients in one query.
    with django_assert_num_queries(4):
        assert client.get(reverse("practice:index")).status_code == 200


def test_new_order_offers_only_own_patients(
    client: Client, general_practitioner: GeneralPractitioner, patient: Patient
) -> None:
    other = make_patient(
        make_general_practitioner("Dr. Demo B"),
        "Test Patient 2",
        RegisteredSex.MALE,
        40,
    )
    response = logged_in(client, general_practitioner).get(
        reverse("practice:new_order")
    )
    assert response.status_code == 200
    assert list(response.context["form"].fields["patient"].queryset) == [patient]
    assert other not in response.context["form"].fields["patient"].queryset


def test_placing_an_order_redirects_to_the_index(
    client: Client, general_practitioner: GeneralPractitioner, patient: Patient
) -> None:
    response = logged_in(client, general_practitioner).post(
        reverse("practice:new_order"),
        {"patient": patient.pk, "test": "cbc", "indication": "non_specific_complaint"},
    )
    assert response.status_code == 302
    assert response["Location"] == reverse("practice:index")
    assert Order.objects.get().patient == patient


def test_service_refusal_is_shown_on_its_field(
    client: Client, general_practitioner: GeneralPractitioner, patient: Patient
) -> None:
    response = logged_in(client, general_practitioner).post(
        reverse("practice:new_order"),
        {"patient": patient.pk, "test": "cbc", "indication": ""},
    )
    assert response.status_code == 200
    errors = response.context["form"].errors.as_data()
    assert [error.code for error in errors["indication"]] == ["indication_required"]
    assert not Order.objects.exists()


def test_another_general_practitioners_patient_is_not_a_valid_choice(
    client: Client, general_practitioner: GeneralPractitioner
) -> None:
    other = make_patient(
        make_general_practitioner("Dr. Demo B"),
        "Test Patient 2",
        RegisteredSex.MALE,
        40,
    )
    response = logged_in(client, general_practitioner).post(
        reverse("practice:new_order"),
        {"patient": other.pk, "test": "ferritin", "indication": ""},
    )
    assert response.status_code == 200
    errors = response.context["form"].errors.as_data()
    assert [error.code for error in errors["patient"]] == ["invalid_choice"]


def test_login_page_and_logout(
    client: Client, general_practitioner: GeneralPractitioner
) -> None:
    assert client.get(reverse("login")).status_code == 200
    logged_in(client, general_practitioner)
    response = client.post(reverse("logout"))
    assert response.status_code == 302
    assert client.get(reverse("practice:index")).status_code == 302


def test_placing_an_order_confirms_it(
    client: Client, general_practitioner: GeneralPractitioner, patient: Patient
) -> None:
    response = logged_in(client, general_practitioner).post(
        reverse("practice:new_order"),
        {"patient": patient.pk, "test": "ferritin", "indication": ""},
        follow=True,
    )
    assertContains(response, "Order placed.")


def test_refusal_page_comes_from_the_kit(client: Client) -> None:
    client.force_login(User.objects.create_user(username="lab"))
    response = client.get(reverse("practice:index"))
    assert response.status_code == 403
    assert "403.html" in [template.name for template in response.templates]


def test_missing_page_comes_from_the_kit(client: Client) -> None:
    response = client.get("/no-such-page/")
    assert response.status_code == 404
    assert "404.html" in [template.name for template in response.templates]


def test_error_page_renders_without_a_request() -> None:
    # Django renders 500.html with no context at all.
    assert "Something went wrong" in render_to_string("500.html")
