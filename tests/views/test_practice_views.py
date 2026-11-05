"""Views of the general practitioner side: status, redirects, form error codes,
query counts."""

import pytest
from django.http import HttpResponseServerError
from django.template.loader import render_to_string
from django.test import Client, RequestFactory
from django.urls import reverse
from django.utils import timezone
from pytest_django import DjangoAssertNumQueries
from pytest_django.asserts import assertContains, assertNotContains
from pytest_django.fixtures import Settings

from tests.conftest import (
    make_general_practitioner,
    make_patient,
    suggest_ferritin_on,
)
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


def logged_in(client: Client, general_practitioner: GeneralPractitioner) -> Client:
    client.force_login(general_practitioner.user)
    return client


def patient_url(patient: Patient) -> str:
    return reverse("practice:patient", kwargs={"pk": patient.pk})


def collect_url(patient: Patient) -> str:
    return reverse("practice:collect_sample", kwargs={"patient": patient.pk})


def order_url(client: Client, patient: Patient, test: OrderedTest) -> str:
    """Collect a sample from the patient; the order page for a test on it. For
    ferritin, the sample first gets a CBC lab report suggesting it (features/ordering.feature)."""
    client.post(collect_url(patient))
    if test == OrderedTest.FERRITIN:
        suggest_ferritin(patient)
    return sample_order_url(patient, test)


def suggest_ferritin(patient: Patient) -> None:
    """The patient's latest sample with a CBC lab report suggesting ferritin."""
    suggest_ferritin_on(patient.samples.latest("pk"), timezone.now())


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
        reverse(
            "practice:new_order",
            kwargs={"patient": patient.pk, "sample": 1, "test": OrderedTest.CBC},
        ),
    ):
        assert client.get(url).status_code == 403
    assert client.post(collect_url(patient)).status_code == 403


def test_navigation_links_to_patients_and_orders(
    client: Client, general_practitioner: GeneralPractitioner
) -> None:
    response = logged_in(client, general_practitioner).get(reverse("practice:patients"))
    assertContains(response, f'href="{reverse("practice:patients")}"')
    assertContains(response, f'href="{reverse("practice:orders")}"')


def test_patients_lists_the_practices_patients(
    client: Client,
    general_practitioner: GeneralPractitioner,
    patient: Patient,
    django_assert_num_queries: DjangoAssertNumQueries,
) -> None:
    make_patient(general_practitioner, "Test Patient 3", RegisteredSex.MALE, 60)
    logged_in(client, general_practitioner)
    # Session, user with general practitioner, patients with their mark.
    with django_assert_num_queries(3):
        response = client.get(reverse("practice:patients"))
    names = [listed.name for listed in response.context["patients"]]
    assert names == ["Test Patient 1", "Test Patient 3"]


def test_patient_page_offers_collecting_a_sample(
    client: Client, general_practitioner: GeneralPractitioner, patient: Patient
) -> None:
    response = logged_in(client, general_practitioner).get(patient_url(patient))
    assert response.context["post_actions"] == [
        {"url": collect_url(patient), "label": "Collect sample"}
    ]
    assert response.context["actions"] == []


def test_patient_page_says_sex_and_age_under_the_name(
    client: Client, general_practitioner: GeneralPractitioner, patient: Patient
) -> None:
    response = logged_in(client, general_practitioner).get(patient_url(patient))
    assert response.context["subtitle"] == "Female, aged 32"
    assertContains(response, "<p>Female, aged 32</p>")


def test_collecting_a_sample_sends_nothing_and_offers_its_tests(
    client: Client, general_practitioner: GeneralPractitioner, patient: Patient
) -> None:
    response = logged_in(client, general_practitioner).post(collect_url(patient))
    sample = patient.samples.get()
    # Straight to the routine first test on the new sample.
    assert response["Location"] == sample_order_url(patient, OrderedTest.CBC)
    assertContains(
        client.get(response["Location"]),
        f'<article role="status" data-level="success">'
        f"Sample {sample.sample_id} collected.</article>",
        html=True,
    )
    assert not Order.objects.exists()
    response = client.get(patient_url(patient))
    assertContains(response, "No tests ordered yet.")
    (item,) = response.context["samples"]
    # Ferritin only beside a lab report suggesting it (features/ordering.feature).
    assert [action["label"] for action in item["actions"]] == ["Order CBC"]


@pytest.mark.parametrize("test", list(OrderedTest))
def test_a_sample_offers_an_order_page_per_test(
    client: Client,
    general_practitioner: GeneralPractitioner,
    patient: Patient,
    test: OrderedTest,
) -> None:
    logged_in(client, general_practitioner)
    url = order_url(client, patient, test)
    assertContains(client.get(patient_url(patient)), f'href="{url}"')
    assert client.get(url).status_code == 200


def test_a_sample_offers_only_tests_it_does_not_have(
    client: Client, general_practitioner: GeneralPractitioner, patient: Patient
) -> None:
    logged_in(client, general_practitioner)
    client.post(order_url(client, patient, OrderedTest.CBC), {"indication": "other"})
    (item,) = client.get(patient_url(patient)).context["samples"]
    # Not ferritin: only beside a lab report suggesting it (features/ordering.feature).
    assert item["actions"] == []


def test_patient_page_queries(
    client: Client,
    general_practitioner: GeneralPractitioner,
    patient: Patient,
    django_assert_num_queries: DjangoAssertNumQueries,
) -> None:
    logged_in(client, general_practitioner)
    client.post(order_url(client, patient, OrderedTest.CBC), {"indication": "other"})
    client.post(order_url(client, patient, OrderedTest.FERRITIN))
    # Session, user with general practitioner, patient, how many laboratories,
    # samples with their laboratory, their orders with lab reports.
    with django_assert_num_queries(6):
        response = client.get(patient_url(patient))
    assert len(response.context["samples"]) == 2


def test_patient_page_offers_ferritin_beside_a_suggestion(
    client: Client,
    general_practitioner: GeneralPractitioner,
    patient: Patient,
    django_assert_num_queries: DjangoAssertNumQueries,
) -> None:
    from web.practice.models import LabReport

    logged_in(client, general_practitioner)
    client.post(order_url(client, patient, OrderedTest.CBC), {"indication": "other"})
    LabReport.objects.create(
        order=Order.objects.get(),
        results={"LBXHGB": 11.2},
        ferritin_suggested=True,
        released_at="2026-10-30T12:00:00+00:00",
        fetched_at="2026-10-30T12:05:00+00:00",
    )
    # As above: whether the sample has ferritin yet comes from its loaded orders.
    with django_assert_num_queries(6):
        response = client.get(patient_url(patient))
    (sample,) = response.context["samples"]
    (entry,) = sample["entries"]
    assert sample["actions"] == []  # ferritin is offered beside the suggestion
    assert entry["order_ferritin_url"] == sample_order_url(
        patient, OrderedTest.FERRITIN
    )
    assertContains(
        response,
        "Ferritin suggested by the hospital&#x27;s screening of this CBC. Likely iron"
        " deficiency; not a diagnosis.",
    )
    assertContains(
        response, "Reference intervals are not shown: the demo has no laboratory's"
    )
    assertContains(response, "Hemoglobin")


def test_patient_page_queries_do_not_grow_with_suggestions(
    client: Client,
    general_practitioner: GeneralPractitioner,
    patient: Patient,
    django_assert_num_queries: DjangoAssertNumQueries,
) -> None:
    from web.practice.models import LabReport

    logged_in(client, general_practitioner)
    for _ in range(2):
        client.post(
            order_url(client, patient, OrderedTest.CBC), {"indication": "other"}
        )
    for order in Order.objects.all():
        LabReport.objects.create(
            order=order,
            results={"LBXHGB": 11.2},
            ferritin_suggested=True,
            released_at="2026-10-30T12:00:00+00:00",
            fetched_at="2026-10-30T12:05:00+00:00",
        )
    with django_assert_num_queries(6):
        response = client.get(patient_url(patient))
    assert len(response.context["samples"]) == 2


def test_unknown_test_is_not_found(
    client: Client, general_practitioner: GeneralPractitioner, patient: Patient
) -> None:
    logged_in(client, general_practitioner).post(collect_url(patient))
    sample = patient.samples.get()
    url = patient_url(patient) + f"samples/{sample.pk}/orders/new/vitamin-d/"
    assert client.get(url).status_code == 404


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
    response = logged_in(client, general_practitioner).get(
        order_url(client, patient, test)
    )
    assert list(response.context["form"].fields) == fields


def test_placing_an_order_returns_to_the_patient_and_confirms(
    client: Client, general_practitioner: GeneralPractitioner, patient: Patient
) -> None:
    response = logged_in(client, general_practitioner).post(
        order_url(client, patient, OrderedTest.CBC),
        {"indication": "unexplained_fatigue"},
    )
    assert response.status_code == 302
    assert response["Location"] == patient_url(patient)
    sample_id = patient.samples.get().sample_id
    assertContains(
        client.get(response["Location"]), f"CBC ordered on sample {sample_id}."
    )
    assert Order.objects.get().sample.patient == patient


def test_ferritin_needs_only_a_confirmation(
    client: Client, general_practitioner: GeneralPractitioner, patient: Patient
) -> None:
    logged_in(client, general_practitioner).post(
        order_url(client, patient, OrderedTest.FERRITIN)
    )
    # Beside the CBC that suggested it, on the same sample.
    assert Order.objects.filter(test=OrderedTest.FERRITIN).count() == 1


def test_service_refusal_is_shown_on_its_field(
    client: Client, general_practitioner: GeneralPractitioner, patient: Patient
) -> None:
    response = logged_in(client, general_practitioner).post(
        order_url(client, patient, OrderedTest.CBC)
    )
    assert response.status_code == 200
    errors = response.context["form"].errors.as_data()
    assert [error.code for error in errors["indication"]] == ["indication_required"]
    # A field's error: the summary's heading, and a link to the field.
    assertContains(response, "There is a problem")
    # The summary links to the first radio button: a radio group's label has no id.
    assertContains(response, '<a href="#id_indication_0">')
    # The group's legend, and the summary's link, name the field without a colon.
    assertContains(response, "<legend>Clinical indication</legend>")
    assertContains(response, "Clinical indication: A CBC needs a clinical indication.")
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
        client.post(order_url(client, each, OrderedTest.CBC), {"indication": "other"})
        client.post(order_url(client, each, OrderedTest.FERRITIN))
    # Each ferritin comes with the CBC whose lab report suggested it.
    assert Order.objects.count() == 6
    # Session, user with general practitioner, orders with their patients, whether
    # there is a laboratory to check for reports.
    with django_assert_num_queries(4):
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
    assert response.content.decode().count("Wrong username or password.") == 1


def sample_order_url(patient: Patient, test: OrderedTest) -> str:
    return reverse(
        "practice:new_order",
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
    client.post(order_url(client, patient, OrderedTest.CBC), {"indication": "other"})
    suggest_ferritin(patient)
    url = sample_order_url(patient, OrderedTest.FERRITIN)
    sample_id = patient.samples.get().sample_id
    assertContains(client.get(url), f"On sample {sample_id}")
    assert client.post(url).status_code == 302
    assert patient.samples.count() == 1
    assert Order.objects.filter(sample__sample_id=sample_id).count() == 2


def test_an_order_that_would_be_refused_returns_to_the_patient(
    client: Client, general_practitioner: GeneralPractitioner, patient: Patient
) -> None:
    # Ferritin without a suggestion (features/ordering.feature), then a test the sample has (features/ordering.feature):
    # opening its order page goes back to the patient, with the refusal there.
    from web.practice.models import NOT_SUGGESTED

    logged_in(client, general_practitioner)
    client.post(order_url(client, patient, OrderedTest.CBC), {"indication": "other"})
    for test, message in (
        (OrderedTest.FERRITIN, NOT_SUGGESTED),
        (OrderedTest.CBC, "This sample already has this test."),
    ):
        response = client.get(sample_order_url(patient, test))
        assert response["Location"] == patient_url(patient), test
        # An error the reader must act on is announced at once; success is not.
        assertContains(
            client.get(patient_url(patient)),
            f'<article role="alert" data-level="error">{message}</article>',
            html=True,
        )
    assert Order.objects.count() == 1


def test_a_stale_form_for_a_test_the_sample_has_returns_to_the_patient(
    client: Client, general_practitioner: GeneralPractitioner, patient: Patient
) -> None:
    # Posted from a page opened before the test was placed (another tab).
    logged_in(client, general_practitioner)
    client.post(order_url(client, patient, OrderedTest.FERRITIN))
    response = client.post(sample_order_url(patient, OrderedTest.FERRITIN))
    assert response["Location"] == patient_url(patient)
    assertContains(
        client.get(patient_url(patient)), "This sample already has this test."
    )
    assert Order.objects.filter(test=OrderedTest.FERRITIN).count() == 1


def test_another_patients_sample_is_not_found(
    client: Client, general_practitioner: GeneralPractitioner, patient: Patient
) -> None:
    other_patient = make_patient(
        general_practitioner, "Test Patient 3", RegisteredSex.MALE, 60
    )
    logged_in(client, general_practitioner)
    client.post(order_url(client, patient, OrderedTest.CBC), {"indication": "other"})
    url = reverse(
        "practice:new_order",
        kwargs={
            "patient": other_patient.pk,
            "sample": patient.samples.get().pk,
            "test": OrderedTest.FERRITIN,
        },
    )
    assert client.post(url).status_code == 404


def test_orders_index_names_each_orders_sample(
    client: Client, general_practitioner: GeneralPractitioner, patient: Patient
) -> None:
    logged_in(client, general_practitioner)
    for _ in range(2):
        client.post(
            order_url(client, patient, OrderedTest.CBC), {"indication": "other"}
        )
    response = client.get(reverse("practice:orders"))
    for sample in patient.samples.all():
        assertContains(response, f'<td class="sample-id">{sample.sample_id}</td>')


def test_order_ferritin_names_its_sample_for_assistive_technology(
    client: Client, general_practitioner: GeneralPractitioner, patient: Patient
) -> None:
    from web.practice.models import LabReport

    logged_in(client, general_practitioner)
    client.post(order_url(client, patient, OrderedTest.CBC), {"indication": "other"})
    order = Order.objects.get()
    LabReport.objects.create(
        order=order,
        results={},
        ferritin_suggested=True,
        released_at="2026-10-30T12:00:00+00:00",
        fetched_at="2026-10-30T12:05:00+00:00",
    )
    response = client.get(patient_url(patient))
    assertContains(
        response, f'aria-label="Order ferritin on sample {order.sample.sample_id}"'
    )


def test_ferritin_ordered_beside_a_suggestion_shows_under_it(
    client: Client, general_practitioner: GeneralPractitioner, patient: Patient
) -> None:
    from web.practice.models import LabReport

    logged_in(client, general_practitioner)
    client.post(order_url(client, patient, OrderedTest.CBC), {"indication": "other"})
    LabReport.objects.create(
        order=Order.objects.get(),
        results={},
        ferritin_suggested=True,
        released_at="2026-10-30T12:00:00+00:00",
        fetched_at="2026-10-30T12:05:00+00:00",
    )
    response = client.post(sample_order_url(patient, OrderedTest.FERRITIN), follow=True)
    sample_id = patient.samples.get().sample_id
    assertContains(response, f"Ferritin ordered on sample {sample_id}.")
    (sample,) = response.context["samples"]
    # The CBC first, then the ferritin ordered beside its suggestion.
    assert [entry["order"].test for entry in sample["entries"]] == ["cbc", "ferritin"]
    assert sample["entries"][0]["order_ferritin_url"] is None
    # No hospital in these tests: the ferritin's lab order is not sent.
    assertContains(response, "<mark>Lab order not sent yet</mark>")


def test_each_sample_is_a_details_block_and_only_the_newest_is_open(
    client: Client, general_practitioner: GeneralPractitioner, patient: Patient
) -> None:
    from web.practice.models import LabReport

    logged_in(client, general_practitioner)
    client.post(order_url(client, patient, OrderedTest.CBC), {"indication": "other"})
    LabReport.objects.create(
        order=Order.objects.get(),
        results={},
        ferritin_suggested=True,
        released_at="2026-10-30T12:00:00+00:00",
        fetched_at="2026-10-30T12:05:00+00:00",
    )
    # The newer sample: a CBC suggesting ferritin, and ferritin beside it.
    client.post(order_url(client, patient, OrderedTest.FERRITIN))
    response = client.get(patient_url(patient))
    newest, older = response.context["samples"]
    assert (newest["open"], newest["tests"], newest["suggested"]) == (
        True,
        "CBC, ferritin",
        True,
    )
    assert (older["open"], older["tests"], older["suggested"]) == (False, "CBC", True)
    assert response.content.decode().count("<details open>") == 1
    assertContains(response, "CBC · Ferritin suggested")


def test_a_patient_without_samples_is_told_how_to_start(
    client: Client, general_practitioner: GeneralPractitioner, patient: Patient
) -> None:
    response = logged_in(client, general_practitioner).get(patient_url(patient))
    assertContains(response, "No samples yet. Collect a sample to order tests.")


def test_patients_can_be_searched_by_name(
    client: Client,
    general_practitioner: GeneralPractitioner,
    patient: Patient,
    django_assert_num_queries: DjangoAssertNumQueries,
) -> None:
    make_patient(general_practitioner, "Maria Peeters", RegisteredSex.FEMALE, 30)
    logged_in(client, general_practitioner)
    with django_assert_num_queries(3):
        response = client.get(reverse("practice:patients"), {"q": "peet"})
    assert [listed.name for listed in response.context["patients"]] == ["Maria Peeters"]
    assertContains(response, 'value="peet"')


def test_the_patients_list_marks_a_patient_awaiting_ferritin(
    client: Client, general_practitioner: GeneralPractitioner, patient: Patient
) -> None:
    from web.practice.models import LabReport

    logged_in(client, general_practitioner)
    client.post(order_url(client, patient, OrderedTest.CBC), {"indication": "other"})
    LabReport.objects.create(
        order=Order.objects.get(),
        results={},
        ferritin_suggested=True,
        released_at="2026-10-30T12:00:00+00:00",
        fetched_at="2026-10-30T12:05:00+00:00",
    )
    # One table: the mark beside the name; Order ferritin is on the patient's
    # page, beside the lab report (features/ordering.feature).
    response = client.get(reverse("practice:patients"))
    assertContains(response, "<mark>Ferritin suggested</mark>", count=1)
    assertNotContains(response, "Ferritin suggested (")
    assertNotContains(response, "Order ferritin")
    client.post(sample_order_url(patient, OrderedTest.FERRITIN))
    assertNotContains(client.get(reverse("practice:patients")), "Ferritin suggested")


def test_an_order_says_whether_its_lab_order_is_sent(
    client: Client, general_practitioner: GeneralPractitioner, patient: Patient
) -> None:
    """Until the hospital has the lab order, there is no report to wait for (features/messaging.feature)."""
    logged_in(client, general_practitioner)
    client.post(order_url(client, patient, OrderedTest.CBC), {"indication": "other"})
    response = client.get(patient_url(patient))
    assertContains(response, "<mark>Lab order not sent yet</mark>")
    assertNotContains(response, "Awaiting lab report")
    Order.objects.update(sent_at="2026-10-30T12:00:00+00:00")
    response = client.get(patient_url(patient))
    assertContains(response, "<mark>Awaiting lab report</mark>")
    assertNotContains(response, "not sent yet")
    # No laboratory to ask, so no hint to check for reports.
    assertNotContains(response, "Check for reports on Orders")


def test_with_several_laboratories_collecting_starts_with_the_choice(
    client: Client, general_practitioner: GeneralPractitioner, patient: Patient
) -> None:
    from web.practice.models import Laboratory

    for name in ("UZ Leuven", "AZ Diest"):
        Laboratory.objects.create(name=name, address="127.0.0.1:1")
    logged_in(client, general_practitioner)
    page = client.get(patient_url(patient))
    # A link to the choice, not a button that collects at once.
    assert page.context["actions"] == [
        {"url": collect_url(patient), "label": "Collect sample"}
    ]
    # Check for reports is the one button, as on any page with a laboratory.
    assert [action["label"] for action in page.context["post_actions"]] == [
        "Check for reports"
    ]
    choice = client.get(collect_url(patient))
    assert [
        str(laboratory)
        for laboratory in choice.context["form"].fields["laboratory"].queryset
    ] == [
        "AZ Diest",
        "UZ Leuven",
    ]
    refused = client.post(collect_url(patient))
    errors = refused.context["form"].errors.as_data()
    assert [error.code for error in errors["laboratory"]] == ["laboratory_required"]
    assert not patient.samples.exists()
    az_diest = Laboratory.objects.get(name="AZ Diest")
    client.post(collect_url(patient), {"laboratory": az_diest.pk})
    assert patient.samples.get().laboratory == az_diest
    assertContains(client.get(patient_url(patient)), ", for AZ Diest</h2>")


def test_the_choice_of_laboratory_starts_at_the_primary_one(
    client: Client, general_practitioner: GeneralPractitioner, patient: Patient
) -> None:
    from web.practice.models import Laboratory

    for name in ("UZ Leuven", "AZ Diest"):
        Laboratory.objects.create(name=name, address="127.0.0.1:1")
    logged_in(client, general_practitioner)
    choice = client.get(collect_url(patient))
    # No primary laboratory: nothing preselected, so the choice stays deliberate.
    assert choice.context["form"]["laboratory"].value() is None
    Laboratory.objects.add(name="UZ Leuven", address="127.0.0.1:1", primary=True)
    choice = client.get(collect_url(patient))
    uz_leuven = Laboratory.objects.get(name="UZ Leuven")
    assert choice.context["form"]["laboratory"].value() == uz_leuven.pk
    assertContains(choice, f'value="{uz_leuven.pk}" id="id_laboratory_1" checked')


def test_with_one_laboratory_collecting_is_one_click(
    client: Client, general_practitioner: GeneralPractitioner, patient: Patient
) -> None:
    from web.practice.models import Laboratory

    only = Laboratory.objects.create(name="AZ Diest", address="127.0.0.1:1")
    logged_in(client, general_practitioner)
    page = client.get(patient_url(patient))
    assert page.context["actions"] == []
    assert page.context["post_actions"][0] == {
        "url": collect_url(patient),
        "label": "Collect sample",
    }
    assert [action["label"] for action in page.context["post_actions"]] == [
        "Collect sample",
        "Check for reports",
    ]
    client.post(collect_url(patient))
    assert patient.samples.get().laboratory == only
