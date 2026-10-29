"""Views of the laboratory side, and moving between the two roles' pages."""

import pytest
from django.test import Client
from django.urls import reverse
from pytest_django import DjangoAssertNumQueries
from pytest_django.asserts import assertContains, assertNotContains

from tests.conftest import (
    make_general_practitioner,
    make_laboratory_staff_member,
    make_patient,
)
from web.lab.models import LaboratoryStaffMember, Sample
from web.practice.models import Order, RegisteredSex
from web.practice.models import Test as OrderedTest

pytestmark = pytest.mark.django_db


@pytest.fixture
def staff_member() -> LaboratoryStaffMember:
    return make_laboratory_staff_member("Lab One")


@pytest.fixture
def order() -> Order:
    owner = make_general_practitioner("Dr. Demo A")
    patient = make_patient(owner, "Test Patient 1", RegisteredSex.FEMALE, 32)
    return Order.objects.create(
        patient=patient,
        test=OrderedTest.FERRITIN,
        registered_sex=patient.registered_sex,
        age=patient.age,
        ordered_at="2026-10-29T09:00Z",
    )


def logged_in(client: Client, staff_member: LaboratoryStaffMember) -> Client:
    client.force_login(staff_member.user)
    return client


def receive_url(order: Order) -> str:
    return reverse("lab:receive", kwargs={"pk": order.pk})


def analyse_url(sample: Sample) -> str:
    return reverse("lab:run_analyser", kwargs={"pk": sample.pk})


def test_samples_queries(
    client: Client,
    staff_member: LaboratoryStaffMember,
    order: Order,
    django_assert_num_queries: DjangoAssertNumQueries,
) -> None:
    logged_in(client, staff_member)
    # Session, user with role, orders to receive, samples to analyse, analysed.
    with django_assert_num_queries(5):
        assert client.get(reverse("lab:samples")).status_code == 200


def test_samples_page_never_shows_a_patient_name(
    client: Client, staff_member: LaboratoryStaffMember, order: Order
) -> None:
    logged_in(client, staff_member)
    assertNotContains(client.get(reverse("lab:samples")), "Test Patient 1")
    client.post(receive_url(order))
    assertNotContains(client.get(reverse("lab:samples")), "Test Patient 1")


def test_receiving_redirects_with_the_sample_id(
    client: Client, staff_member: LaboratoryStaffMember, order: Order
) -> None:
    response = logged_in(client, staff_member).post(receive_url(order))
    assert response["Location"] == reverse("lab:samples")
    sample = Sample.objects.get()
    assertContains(
        client.get(response["Location"]), f"Sample {sample.sample_id} received."
    )


def test_receiving_twice_is_refused_with_a_message(
    client: Client, staff_member: LaboratoryStaffMember, order: Order
) -> None:
    logged_in(client, staff_member).post(receive_url(order))
    response = client.post(receive_url(order), follow=True)
    assertContains(response, "already been received")
    assert Sample.objects.count() == 1


def test_running_the_analyser(
    client: Client, staff_member: LaboratoryStaffMember, order: Order
) -> None:
    logged_in(client, staff_member).post(receive_url(order))
    sample = Sample.objects.get()
    response = client.post(analyse_url(sample))
    assert response["Location"] == reverse("lab:samples")
    sample.refresh_from_db()
    assert sample.analysed_at is not None


def test_actions_are_post_only(
    client: Client, staff_member: LaboratoryStaffMember, order: Order
) -> None:
    logged_in(client, staff_member)
    assert client.get(receive_url(order)).status_code == 405
    client.post(receive_url(order))
    assert client.get(analyse_url(Sample.objects.get())).status_code == 405


def test_general_practitioner_is_sent_to_their_start_page(client: Client) -> None:
    client.force_login(make_general_practitioner("Dr. Demo A").user)
    response = client.get(reverse("lab:samples"), follow=True)
    assert response.redirect_chain == [(reverse("practice:patients"), 302)]
    assertContains(response, "That page is for laboratory staff.")


def test_laboratory_staff_are_sent_to_their_start_page(
    client: Client, staff_member: LaboratoryStaffMember
) -> None:
    response = logged_in(client, staff_member).get(
        reverse("practice:patients"), follow=True
    )
    assert response.redirect_chain == [(reverse("lab:samples"), 302)]
    assertContains(response, "That page is for general practitioners.")


def test_general_practitioner_cannot_receive(client: Client, order: Order) -> None:
    client.force_login(order.patient.general_practitioner.user)
    client.post(receive_url(order))
    assert not Sample.objects.exists()
