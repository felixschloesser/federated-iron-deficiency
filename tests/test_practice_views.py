"""Views of the general practitioner side: status, redirects, form error codes,
query counts."""

import pytest
from django.http import HttpResponseServerError
from django.template.loader import render_to_string
from django.test import Client, RequestFactory
from django.urls import reverse
from pytest_django import DjangoAssertNumQueries
from pytest_django.asserts import assertContains
from pytest_django.fixtures import Settings

from tests.conftest import make_general_practitioner, make_patient
from web.accounts.models import User
from web.practice.models import GeneralPractitioner, Order, Patient
from web.views import ServerErrorView
from web.vocabulary import RegisteredSex
from web.vocabulary import Test as OrderedTest

pytestmark = pytest.mark.django_db


@pytest.fixture
def general_practitioner() -> GeneralPractitioner:
    return make_general_practitioner("Dr. Demo A")


@pytest.fixture
def patient(general_practitioner: GeneralPractitioner) -> Patient:
    return make_patient(
        general_practitioner, "Test Patient 1", RegisteredSex.FEMALE, 32
    )


@pytest.fixture
def other_patient() -> Patient:
    other = make_general_practitioner("Dr. Demo B")
    return make_patient(other, "Test Patient 2", RegisteredSex.MALE, 40)


def logged_in(client: Client, general_practitioner: GeneralPractitioner) -> Client:
    client.force_login(general_practitioner.user)
    return client


def patient_url(patient: Patient) -> str:
    return reverse("practice:patient", kwargs={"pk": patient.pk})


def order_url(patient: Patient, test: OrderedTest) -> str:
    return reverse("practice:new_order", kwargs={"patient": patient.pk, "test": test})


def test_anonymous_is_sent_to_login(client: Client) -> None:
    response = client.get(reverse("practice:patients"))
    assert response.status_code == 302
    assert response["Location"].startswith(reverse("login"))


def test_account_without_a_role_is_refused(client: Client, patient: Patient) -> None:
    client.force_login(User.objects.create_user(username="no-role"))
    for url in (
        reverse("practice:patients"),
        reverse("practice:orders"),
        patient_url(patient),
        order_url(patient, OrderedTest.CBC),
    ):
        assert client.get(url).status_code == 403


def test_navigation_links_to_patients_and_orders(
    client: Client, general_practitioner: GeneralPractitioner
) -> None:
    response = logged_in(client, general_practitioner).get(reverse("practice:patients"))
    assertContains(response, f'href="{reverse("practice:patients")}"')
    assertContains(response, f'href="{reverse("practice:orders")}"')


def test_patients_lists_only_own_patients(
    client: Client,
    general_practitioner: GeneralPractitioner,
    patient: Patient,
    other_patient: Patient,
    django_assert_num_queries: DjangoAssertNumQueries,
) -> None:
    make_patient(general_practitioner, "Test Patient 3", RegisteredSex.MALE, 60)
    logged_in(client, general_practitioner)
    # Session, user with general practitioner, patients.
    with django_assert_num_queries(3):
        response = client.get(reverse("practice:patients"))
    names = [listed.name for listed in response.context["patients"]]
    assert names == ["Test Patient 1", "Test Patient 3"]


@pytest.mark.parametrize("test", list(OrderedTest))
def test_patient_page_offers_an_order_page_per_test(
    client: Client,
    general_practitioner: GeneralPractitioner,
    patient: Patient,
    test: OrderedTest,
) -> None:
    logged_in(client, general_practitioner)
    assertContains(
        client.get(patient_url(patient)), f'href="{order_url(patient, test)}"'
    )
    assert client.get(order_url(patient, test)).status_code == 200


def test_patient_page_queries(
    client: Client,
    general_practitioner: GeneralPractitioner,
    patient: Patient,
    django_assert_num_queries: DjangoAssertNumQueries,
) -> None:
    logged_in(client, general_practitioner)
    client.post(order_url(patient, OrderedTest.CBC), {"indication": "other"})
    client.post(order_url(patient, OrderedTest.FERRITIN))
    # Session, user with general practitioner, patient, orders with lab reports.
    with django_assert_num_queries(4):
        response = client.get(patient_url(patient))
    assert len(response.context["entries"]) == 2


def test_patient_page_offers_ferritin_beside_a_suggestion(
    client: Client,
    general_practitioner: GeneralPractitioner,
    patient: Patient,
    django_assert_num_queries: DjangoAssertNumQueries,
) -> None:
    from web.practice.models import LabReport

    logged_in(client, general_practitioner)
    client.post(order_url(patient, OrderedTest.CBC), {"indication": "other"})
    LabReport.objects.create(
        order=Order.objects.get(),
        results={"LBXHGB": 11.2},
        ferritin_suggested=True,
        released_at="2026-10-30T12:00:00+00:00",
        fetched_at="2026-10-30T12:05:00+00:00",
    )
    # As above, and whether the patient has ferritin yet.
    with django_assert_num_queries(5):
        response = client.get(patient_url(patient))
    (entry,) = response.context["entries"]
    assert entry["order_ferritin_url"] == sample_order_url(
        patient, OrderedTest.FERRITIN
    )
    assertContains(response, "Ferritin suggested.")
    assertContains(response, "Hemoglobin")


def test_another_general_practitioners_patient_is_not_found(
    client: Client, general_practitioner: GeneralPractitioner, other_patient: Patient
) -> None:
    logged_in(client, general_practitioner)
    assert client.get(patient_url(other_patient)).status_code == 404
    url = order_url(other_patient, OrderedTest.FERRITIN)
    assert client.get(url).status_code == 404
    assert client.post(url).status_code == 404
    assert not Order.objects.exists()


def test_unknown_test_is_not_found(
    client: Client, general_practitioner: GeneralPractitioner, patient: Patient
) -> None:
    url = patient_url(patient) + "orders/new/vitamin-d/"
    assert logged_in(client, general_practitioner).get(url).status_code == 404


@pytest.mark.parametrize(
    ("test", "fields"),
    [(OrderedTest.CBC, ["indication"]), (OrderedTest.FERRITIN, [])],
)
def test_order_form_asks_only_what_the_test_needs(
    client: Client,
    general_practitioner: GeneralPractitioner,
    patient: Patient,
    test: OrderedTest,
    fields: list[str],
) -> None:
    response = logged_in(client, general_practitioner).get(order_url(patient, test))
    assert list(response.context["form"].fields) == fields


def test_placing_an_order_returns_to_the_patient_and_confirms(
    client: Client, general_practitioner: GeneralPractitioner, patient: Patient
) -> None:
    response = logged_in(client, general_practitioner).post(
        order_url(patient, OrderedTest.CBC), {"indication": "unexplained_fatigue"}
    )
    assert response.status_code == 302
    assert response["Location"] == patient_url(patient)
    assertContains(client.get(response["Location"]), "Order placed.")
    assert Order.objects.get().sample.patient == patient


def test_ferritin_needs_only_a_confirmation(
    client: Client, general_practitioner: GeneralPractitioner, patient: Patient
) -> None:
    logged_in(client, general_practitioner).post(
        order_url(patient, OrderedTest.FERRITIN)
    )
    assert Order.objects.get().test == OrderedTest.FERRITIN


def test_service_refusal_is_shown_on_its_field(
    client: Client, general_practitioner: GeneralPractitioner, patient: Patient
) -> None:
    response = logged_in(client, general_practitioner).post(
        order_url(patient, OrderedTest.CBC)
    )
    assert response.status_code == 200
    errors = response.context["form"].errors.as_data()
    assert [error.code for error in errors["indication"]] == ["indication_required"]
    assert not Order.objects.exists()


def test_orders_queries(
    client: Client,
    general_practitioner: GeneralPractitioner,
    patient: Patient,
    django_assert_num_queries: DjangoAssertNumQueries,
) -> None:
    logged_in(client, general_practitioner)
    other = make_patient(general_practitioner, "Test Patient 3", RegisteredSex.MALE, 60)
    for each in (patient, other):
        client.post(order_url(each, OrderedTest.CBC), {"indication": "other"})
        client.post(order_url(each, OrderedTest.FERRITIN))
    assert Order.objects.count() == 4
    # Session, user with general practitioner, orders with their patients.
    with django_assert_num_queries(3):
        assert client.get(reverse("practice:orders")).status_code == 200


def test_login_page_and_logout(
    client: Client, general_practitioner: GeneralPractitioner
) -> None:
    assert client.get(reverse("login")).status_code == 200
    logged_in(client, general_practitioner)
    response = client.post(reverse("logout"))
    assert response.status_code == 302
    assert client.get(reverse("practice:patients")).status_code == 302


def test_refusal_page_comes_from_the_kit(client: Client) -> None:
    client.force_login(User.objects.create_user(username="no-role"))
    response = client.get(reverse("practice:patients"))
    assert response.status_code == 403
    assert "403.html" in [template.name for template in response.templates]


def test_missing_page_comes_from_the_kit(client: Client) -> None:
    response = client.get("/no-such-page/")
    assert response.status_code == 404
    assert "404.html" in [template.name for template in response.templates]


def test_error_page_renders_without_a_request() -> None:
    # Django's own handler renders 500.html with no context at all.
    assert "Something went wrong" in render_to_string("500.html")


def test_error_page_names_the_hospital(settings: Settings) -> None:
    settings.PARTY_NAME = "AZ Diest"
    response = ServerErrorView.as_view()(RequestFactory().get("/"))
    assert isinstance(response, HttpResponseServerError)
    assert b"<title>Something went wrong \xc2\xb7 AZ Diest</title>" in response.content


def test_form_error_is_shown_once_in_the_summary(client: Client) -> None:
    response = client.post(reverse("login"), {"username": "x", "password": "y"})
    assert response.content.decode().count("Please enter a correct username") == 1


def test_patient_page_offers_every_test_on_a_new_sample(
    client: Client, general_practitioner: GeneralPractitioner, patient: Patient
) -> None:
    logged_in(client, general_practitioner)
    client.post(order_url(patient, OrderedTest.CBC), {"indication": "other"})
    response = client.get(patient_url(patient))
    assert [action["label"] for action in response.context["actions"]] == [
        "Order CBC",
        "Order ferritin",
    ]
    client.post(order_url(patient, OrderedTest.CBC), {"indication": "other"})
    assert patient.samples.count() == 2


def sample_order_url(patient: Patient, test: OrderedTest) -> str:
    return reverse(
        "practice:new_order_on_sample",
        kwargs={
            "patient": patient.pk,
            "sample": patient.samples.latest("pk").pk,
            "test": test,
        },
    )


def test_ordering_on_a_sample_says_so_and_adds_no_sample(
    client: Client, general_practitioner: GeneralPractitioner, patient: Patient
) -> None:
    logged_in(client, general_practitioner)
    client.post(order_url(patient, OrderedTest.CBC), {"indication": "other"})
    url = sample_order_url(patient, OrderedTest.FERRITIN)
    sample_id = patient.samples.get().sample_id
    assertContains(client.get(url), f"On sample {sample_id}")
    assert client.post(url).status_code == 302
    assert patient.samples.count() == 1
    assert Order.objects.filter(sample__sample_id=sample_id).count() == 2


def test_a_test_the_sample_has_is_refused_in_the_summary(
    client: Client, general_practitioner: GeneralPractitioner, patient: Patient
) -> None:
    logged_in(client, general_practitioner)
    client.post(order_url(patient, OrderedTest.FERRITIN))
    response = client.post(sample_order_url(patient, OrderedTest.FERRITIN))
    errors = response.context["form"].non_field_errors().as_data()
    assert [error.code for error in errors] == ["already_ordered"]


def test_another_patients_sample_is_not_found(
    client: Client, general_practitioner: GeneralPractitioner, patient: Patient
) -> None:
    other_patient = make_patient(
        general_practitioner, "Test Patient 3", RegisteredSex.MALE, 60
    )
    logged_in(client, general_practitioner)
    client.post(order_url(patient, OrderedTest.CBC), {"indication": "other"})
    url = reverse(
        "practice:new_order_on_sample",
        kwargs={
            "patient": other_patient.pk,
            "sample": patient.samples.get().pk,
            "test": OrderedTest.FERRITIN,
        },
    )
    assert client.post(url).status_code == 404
