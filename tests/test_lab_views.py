"""Views of the laboratory side, and moving between the two roles' pages."""

from datetime import UTC, datetime

import pytest
from django.test import Client
from django.urls import reverse
from pytest_django import DjangoAssertNumQueries
from pytest_django.asserts import assertContains, assertNotContains

from tests.conftest import (
    deliver,
    make_general_practitioner,
    make_laboratory_staff_member,
    make_patient,
)
from web.lab.models import LaboratoryStaffMember, LabOrder
from web.practice import services
from web.vocabulary import RegisteredSex
from web.vocabulary import Test as OrderedTest

pytestmark = pytest.mark.django_db


@pytest.fixture
def staff_member() -> LaboratoryStaffMember:
    return make_laboratory_staff_member("Lab One")


@pytest.fixture
def lab_order() -> LabOrder:
    """A ferritin ordered by a general practitioner, as the lab received it (DF23)."""
    owner = make_general_practitioner("Dr. Demo A")
    patient = make_patient(owner, "Test Patient 1", RegisteredSex.FEMALE, 32)
    order = services.place_order(
        general_practitioner=owner,
        patient=patient,
        test=OrderedTest.FERRITIN,
        indication=None,
        now=datetime(2026, 10, 29, 9, 0, tzinfo=UTC),
    )
    deliver(order)
    return LabOrder.objects.select_related("sample").get()


def logged_in(client: Client, staff_member: LaboratoryStaffMember) -> Client:
    client.force_login(staff_member.user)
    return client


def analyse_url(lab_order: LabOrder) -> str:
    return reverse("lab:run_analyser", kwargs={"pk": lab_order.pk})


@pytest.mark.parametrize("page", ["lab:to_analyse", "lab:analysed"])
def test_lab_index_queries(
    client: Client,
    staff_member: LaboratoryStaffMember,
    lab_order: LabOrder,
    django_assert_num_queries: DjangoAssertNumQueries,
    page: str,
) -> None:
    logged_in(client, staff_member)
    # Session, user with role, lab orders with their samples.
    with django_assert_num_queries(3):
        assert client.get(reverse(page)).status_code == 200


def test_lab_pages_never_show_a_patient_name(
    client: Client, staff_member: LaboratoryStaffMember, lab_order: LabOrder
) -> None:
    logged_in(client, staff_member)
    assertNotContains(client.get(reverse("lab:to_analyse")), "Test Patient 1")
    client.post(analyse_url(lab_order))
    assertNotContains(client.get(reverse("lab:analysed")), "Test Patient 1")


def test_navigation_links_to_both_lab_pages(
    client: Client, staff_member: LaboratoryStaffMember
) -> None:
    response = logged_in(client, staff_member).get(reverse("lab:to_analyse"))
    assertContains(response, f'href="{reverse("lab:to_analyse")}"')
    assertContains(response, f'href="{reverse("lab:analysed")}"')


def test_running_the_analyser(
    client: Client, staff_member: LaboratoryStaffMember, lab_order: LabOrder
) -> None:
    response = logged_in(client, staff_member).post(analyse_url(lab_order))
    assert response["Location"] == reverse("lab:to_analyse")
    assertContains(
        client.get(response["Location"]),
        f"Sample {lab_order.sample.sample_id}: ferritin analysed.",
    )
    lab_order.refresh_from_db()
    assert lab_order.analysed_at is not None


def test_actions_are_post_only(
    client: Client, staff_member: LaboratoryStaffMember, lab_order: LabOrder
) -> None:
    logged_in(client, staff_member)
    assert client.get(analyse_url(lab_order)).status_code == 405


def test_general_practitioner_is_sent_to_their_start_page(client: Client) -> None:
    client.force_login(make_general_practitioner("Dr. Demo A").user)
    response = client.get(reverse("lab:to_analyse"), follow=True)
    assert response.redirect_chain == [(reverse("practice:patients"), 302)]
    assertContains(response, "That page is for laboratory staff.")


def test_laboratory_staff_are_sent_to_their_start_page(
    client: Client, staff_member: LaboratoryStaffMember
) -> None:
    response = logged_in(client, staff_member).get(
        reverse("practice:patients"), follow=True
    )
    assert response.redirect_chain == [(reverse("lab:to_analyse"), 302)]
    assertContains(response, "That page is for general practitioners.")


def test_general_practitioner_cannot_run_the_analyser(
    client: Client, lab_order: LabOrder
) -> None:
    from web.practice.models import GeneralPractitioner

    client.force_login(GeneralPractitioner.objects.get().user)
    client.post(analyse_url(lab_order))
    lab_order.refresh_from_db()
    assert lab_order.analysed_at is None


def cbc_lab_order(sex: RegisteredSex) -> LabOrder:
    """A CBC for a non-specific complaint, aged 32, as the lab received it (DF23)."""
    from web.vocabulary import ClinicalIndication

    owner = make_general_practitioner("Dr. Demo A")
    patient = make_patient(owner, "Test Patient 1", sex, 32)
    order = services.place_order(
        general_practitioner=owner,
        patient=patient,
        test=OrderedTest.CBC,
        indication=ClinicalIndication.NON_SPECIFIC_COMPLAINT,
        now=datetime(2026, 10, 29, 9, 0, tzinfo=UTC),
    )
    deliver(order)
    return LabOrder.objects.select_related("sample").get()


def test_a_cbc_not_screened_for_a_model_problem_warns(
    client: Client, staff_member: LaboratoryStaffMember
) -> None:
    lab_order = cbc_lab_order(RegisteredSex.FEMALE)
    response = logged_in(client, staff_member).post(analyse_url(lab_order), follow=True)
    assertContains(response, 'data-level="warning"')
    assertContains(
        response,
        f"Sample {lab_order.sample.sample_id}: CBC analysed and released, not"
        " screened: no model deployed. Tell the laboratory director.",
    )


def test_a_cbc_not_screened_for_eligibility_does_not_warn(
    client: Client, staff_member: LaboratoryStaffMember
) -> None:
    lab_order = cbc_lab_order(RegisteredSex.MALE)
    response = logged_in(client, staff_member).post(analyse_url(lab_order), follow=True)
    assertNotContains(response, 'data-level="warning"')
    assertContains(response, f"Sample {lab_order.sample.sample_id}: CBC analysed.")
