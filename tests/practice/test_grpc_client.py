"""The general practitioner's app sending lab orders and fetching lab reports
over gRPC, and its pages and commands that do. The hospital is the stand-in
tests/practice/fake_laboratory.py: no hospital code, no hospital database; the
real endpoint is held to the same messages by tests/hospital/test_grpc_server.py."""

from datetime import UTC, datetime

import grpc
import pytest
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.test import Client
from django.urls import reverse
from pytest_django.asserts import assertContains, assertNotContains
from pytest_django.fixtures import Settings

from tests.practice.conftest import (
    Running,
    collect_and_order,
    make_general_practitioner,
    make_patient,
    suggest_ferritin_on,
)
from tests.practice.fake_laboratory import FakeLaboratory
from web.practice import grpc_client
from web.practice.models import Laboratory, LabReport, Order, Patient
from web.shared.accounts.models import User
from web.shared.grpc import messages_pb2
from web.shared.grpc.convert import to_proto
from web.shared.vocabulary import ClinicalIndication, RegisteredSex
from web.shared.vocabulary import Test as OrderedTest

NOW = datetime(2026, 10, 30, 10, 0, tzinfo=UTC)
# The stand-in serves from its own threads; the app's database stays in the test.
pytestmark = pytest.mark.django_db


def latest_sample_id(patient: Patient) -> str:
    """The sample ID of the patient's latest sample."""
    return patient.samples.latest("pk").sample_id.value


@pytest.fixture
def practice(settings: Settings, fake_laboratory: Running) -> Laboratory:
    """Practice "De Ceder", working with the laboratory "AZ Diest"."""
    settings.PRACTICE_NAME = "De Ceder"
    return Laboratory.objects.create(name="AZ Diest", address=fake_laboratory.address)


@pytest.fixture
def owner() -> User:
    return make_general_practitioner("Dr. Demo A")


# The app against the endpoint: its messages, sent and fetched.


def send_cbc(laboratory: Laboratory, indication: ClinicalIndication) -> Order:
    """Order a CBC for a new patient and send the pending lab orders."""
    record = make_patient("Test Patient 1", RegisteredSex.FEMALE, 32)
    placed = collect_and_order(
        patient=record, test=OrderedTest.CBC, indication=indication, now=NOW
    )
    grpc_client.send_pending_lab_orders(laboratory, now=NOW)
    return placed


def test_a_placed_order_reaches_the_hospital_as_its_lab_order(
    practice: Laboratory, fake_laboratory: Running
) -> None:
    placed = send_cbc(practice, ClinicalIndication.UNEXPLAINED_FATIGUE)
    (sent,) = fake_laboratory.laboratory.lab_orders
    assert sent.sample_id == placed.sample.sample_id.value
    assert sent.test == messages_pb2.TEST_CBC
    assert (
        sent.clinical_indication == messages_pb2.CLINICAL_INDICATION_UNEXPLAINED_FATIGUE
    )
    assert sent.registered_sex == messages_pb2.REGISTERED_SEX_FEMALE
    assert sent.age == 32
    assert sent.ordered_at.ToDatetime(tzinfo=UTC) == NOW
    # The practice by its name's slug, in the call's metadata; no general
    # practitioner.
    assert fake_laboratory.laboratory.callers == ["de-ceder"]


def place_cbc(name: str) -> Order:
    """A CBC order for a new patient, not sent yet."""
    record = make_patient(name, RegisteredSex.FEMALE, 32)
    return collect_and_order(
        patient=record,
        test=OrderedTest.CBC,
        indication=ClinicalIndication.UNEXPLAINED_FATIGUE,
        now=NOW,
    )


AGE_REQUIRED = [("age", "This field is required.")]


def test_a_rejected_lab_order_keeps_its_reason_and_is_sent_no_more(
    practice: Laboratory, fake_laboratory: Running
) -> None:
    """The laboratory's reason for rejection (WHO LQMS 5-4, p. 66) is kept on the
    order, which is never sent again: the general practitioner orders anew."""
    placed = place_cbc("Test Patient 1")
    fake_laboratory.laboratory.rejects[placed.sample.sample_id.value] = AGE_REQUIRED
    grpc_client.send_pending_lab_orders(practice, now=NOW)
    grpc_client.send_pending_lab_orders(practice, now=NOW)
    order = Order.objects.get(pk=placed.pk)
    assert (order.rejected_at, order.sent_at) == (NOW, None)
    assert order.reason_for_rejection == "age: This field is required."
    assert fake_laboratory.laboratory.lab_orders == []
    assert len(fake_laboratory.laboratory.callers) == 1


def test_a_rejected_lab_order_holds_back_no_other_and_reports_still_arrive(
    practice: Laboratory, fake_laboratory: Running
) -> None:
    """One lab order the laboratory rejects is that order's fault alone."""
    rejected = place_cbc("Test Patient 2")
    fake_laboratory.laboratory.rejects[rejected.sample.sample_id.value] = AGE_REQUIRED
    accepted = place_cbc("Test Patient 3")
    placed, report_id = released_ferritin(fake_laboratory.laboratory)
    assert grpc_client.check_for_lab_reports(practice, now=NOW) == 1
    sent = [order.sample_id for order in fake_laboratory.laboratory.lab_orders]
    assert accepted.sample.sample_id.value in sent
    assert LabReport.objects.filter(order=placed).exists()
    assert report_id in fake_laboratory.laboratory.acknowledged


def test_placing_an_order_the_laboratory_rejects_says_why(
    client: Client, practice: Laboratory, owner: User, fake_laboratory: Running
) -> None:
    record = make_patient("Test Patient 1", RegisteredSex.FEMALE, 32)
    client.force_login(owner)
    url = new_order_url(client, record)
    fake_laboratory.laboratory.rejects[latest_sample_id(record)] = AGE_REQUIRED
    response = client.post(url, follow=True)
    assertContains(
        response, "AZ Diest rejected the lab order: age: This field is required."
    )
    assertNotContains(response, "refused")


def test_the_patient_page_shows_a_rejected_lab_order_and_its_reason(
    client: Client, practice: Laboratory, owner: User
) -> None:
    placed = place_cbc("Test Patient 1")
    placed.reject(reason="age: This field is required.", now=NOW)
    client.force_login(owner)
    response = client.get(
        reverse("practice:patient", kwargs={"pk": placed.sample.patient.pk})
    )
    assertContains(response, "Lab order rejected: age: This field is required.")
    assertContains(response, "Collect a new sample to order again.")
    assertNotContains(response, "Lab order not sent yet")


def test_the_hint_to_order_again_follows_the_order_date(
    client: Client, practice: Laboratory, owner: User
) -> None:
    """The status, then when it was ordered, then what to do, as for a lab
    order awaiting its lab report."""
    placed = place_cbc("Test Patient 1")
    placed.reject(reason="age: This field is required.", now=NOW)
    client.force_login(owner)
    response = client.get(
        reverse("practice:patient", kwargs={"pk": placed.sample.patient.pk})
    )
    html = response.content.decode()
    assert html.index("Lab order rejected") < html.index("Ordered ")
    assert html.index("Ordered ") < html.index("Collect a new sample to order again.")


def test_a_closed_sample_says_its_lab_order_was_rejected(
    client: Client, practice: Laboratory, owner: User
) -> None:
    """Older samples start closed; a rejection shows on their summary all the same."""
    rejected = place_cbc("Test Patient 1")
    rejected.reject(reason="age: This field is required.", now=NOW)
    record = rejected.sample.patient
    collect_and_order(
        patient=record,
        test=OrderedTest.CBC,
        indication=ClinicalIndication.UNEXPLAINED_FATIGUE,
        now=NOW,
    )
    client.force_login(owner)
    response = client.get(reverse("practice:patient", kwargs={"pk": record.pk}))
    assertContains(response, "<small>CBC · Lab order rejected</small>", html=False)


def test_the_orders_page_says_a_lab_order_was_rejected(
    client: Client, practice: Laboratory, owner: User
) -> None:
    placed = place_cbc("Test Patient 1")
    placed.reject(reason="age: This field is required.", now=NOW)
    client.force_login(owner)
    response = client.get(reverse("practice:orders"))
    assertContains(response, '<td data-label="Lab report">Lab order rejected</td>')


def test_a_practice_without_a_name_sends_nothing(
    settings: Settings, practice: Laboratory, fake_laboratory: Running
) -> None:
    """A practice nobody named claims no default name: it refuses to call."""
    settings.PRACTICE_NAME = None
    with pytest.raises(ImproperlyConfigured):
        send_cbc(practice, ClinicalIndication.UNEXPLAINED_FATIGUE)
    assert fake_laboratory.laboratory.callers == []


@pytest.mark.parametrize("indication", list(ClinicalIndication))
def test_the_lab_order_names_the_indication_for_the_hospital_to_decide(
    practice: Laboratory, fake_laboratory: Running, indication: ClinicalIndication
) -> None:
    """The laboratory, not the practice, decides whether an indication is
    screened (features/hospital/screening.feature): the lab order names it."""
    send_cbc(practice, indication)
    (sent,) = fake_laboratory.laboratory.lab_orders
    assert sent.clinical_indication == to_proto(
        indication, messages_pb2.ClinicalIndication
    )


def released_ferritin(
    laboratory: FakeLaboratory, *, ferritin_suggested: bool = False
) -> tuple[Order, int]:
    """A patient's ferritin order, analysed and released at the hospital; the
    order and the lab report's ID."""
    record = make_patient("Test Patient 1", RegisteredSex.FEMALE, 32)
    placed = collect_and_order(
        patient=record, test=OrderedTest.FERRITIN, indication=None, now=NOW
    )
    report_id = laboratory.release(
        placed.sample.sample_id.value,
        messages_pb2.TEST_FERRITIN,
        NOW,
        ferritin_suggested=ferritin_suggested,
    )
    return placed, report_id


def test_checking_fetches_a_lab_report_and_acknowledges_it(
    practice: Laboratory, fake_laboratory: Running
) -> None:
    placed, report_id = released_ferritin(
        fake_laboratory.laboratory, ferritin_suggested=True
    )
    assert grpc_client.check_for_lab_reports(practice, now=NOW) == 1
    assert LabReport.objects.get(order=placed).ferritin_suggested is True
    assert report_id in fake_laboratory.laboratory.acknowledged


def test_a_lab_report_is_fetched_once(
    practice: Laboratory, fake_laboratory: Running
) -> None:
    placed, report_id = released_ferritin(fake_laboratory.laboratory)
    grpc_client.check_for_lab_reports(practice, now=NOW)
    # The stand-in forgets the acknowledgement: the app still stores it once.
    fake_laboratory.laboratory.acknowledged.discard(report_id)
    grpc_client.check_for_lab_reports(practice, now=NOW)
    assert LabReport.objects.filter(order=placed).count() == 1


def test_a_lab_report_the_app_cannot_match_does_not_block_the_others(
    practice: Laboratory, fake_laboratory: Running
) -> None:
    placed, report_id = released_ferritin(fake_laboratory.laboratory)
    stranger = fake_laboratory.laboratory.release(
        "999999-1", messages_pb2.TEST_FERRITIN, NOW
    )
    assert grpc_client.check_for_lab_reports(practice, now=NOW) == 1
    assert LabReport.objects.filter(order=placed).exists()
    assert report_id in fake_laboratory.laboratory.acknowledged
    assert stranger not in fake_laboratory.laboratory.acknowledged


# Each part of a lab report, from its descriptor, so a new part is covered too.
PARTS = [
    field.name
    for field in messages_pb2.LabReport.DESCRIPTOR.fields
    if not field.is_repeated
]


@pytest.mark.parametrize("part", PARTS)
def test_a_lab_report_missing_any_part_is_not_stored(
    practice: Laboratory, fake_laboratory: Running, part: str
) -> None:
    """A lab report is complete or not stored (messages.proto): the practice
    never fills a part the hospital left out, such as no ferritin suggestion."""
    placed, report_id = released_ferritin(fake_laboratory.laboratory)
    full = fake_laboratory.laboratory.reports[report_id]
    fake_laboratory.laboratory.reports[report_id] = messages_pb2.LabReport(
        **{
            field.name: getattr(full, field.name)
            for field in full.DESCRIPTOR.fields
            if field.name != part
        }
    )
    assert grpc_client.check_for_lab_reports(practice, now=NOW) == 0
    assert not LabReport.objects.filter(order=placed).exists()
    assert fake_laboratory.laboratory.acknowledged == set()


# The general practitioner's app in use: its views and command talk to the endpoint.


def new_order_url(client: Client, record: Patient) -> str:
    """Collect a sample from the patient; the ferritin order page on it, beside
    a CBC lab report suggesting ferritin (features/practice/ordering.feature)."""
    client.post(reverse("practice:collect_sample", kwargs={"patient": record.pk}))
    suggest_ferritin_on(record.samples.latest("pk"), NOW)
    return reverse(
        "practice:order",
        kwargs={
            "patient": record.pk,
            "sample": record.samples.latest("pk").pk,
            "test": OrderedTest.FERRITIN,
        },
    )


def test_placing_an_order_sends_its_lab_order(
    client: Client, practice: Laboratory, owner: User, fake_laboratory: Running
) -> None:
    record = make_patient("Test Patient 1", RegisteredSex.FEMALE, 32)
    client.force_login(owner)
    client.post(new_order_url(client, record))
    assert [sent.sample_id for sent in fake_laboratory.laboratory.lab_orders] == [
        latest_sample_id(record)
    ]
    assert Order.objects.get(test=OrderedTest.FERRITIN).sent_at is not None


def test_an_unreachable_hospital_gets_the_order_with_the_next_check(
    client: Client, practice: Laboratory, owner: User
) -> None:
    Laboratory.objects.update(address="127.0.0.1:1")
    record = make_patient("Test Patient 1", RegisteredSex.FEMALE, 32)
    client.force_login(owner)
    response = client.post(new_order_url(client, record), follow=True)
    assertContains(response, "Ferritin ordered on sample")
    assertContains(
        response, "AZ Diest could not be reached, so the lab order is not sent yet."
    )
    assertNotContains(response, "next check")
    assert Order.objects.get(test=OrderedTest.FERRITIN).sent_at is None


def test_a_hospital_refusing_a_lab_order_is_not_called_unreachable(
    client: Client, practice: Laboratory, owner: User, fake_laboratory: Running
) -> None:
    """A message the hospital rejects (INVALID_ARGUMENT) is a fault to report,
    not a network problem to wait out."""
    fake_laboratory.laboratory.refusal = grpc.StatusCode.INVALID_ARGUMENT
    record = make_patient("Test Patient 1", RegisteredSex.FEMALE, 32)
    collect_and_order(
        patient=record, test=OrderedTest.FERRITIN, indication=None, now=NOW
    )
    client.force_login(owner)
    response = client.post(reverse("practice:check_for_reports"), follow=True)
    assertNotContains(response, "could not be reached")
    assertContains(response, "AZ Diest refused a message. Tell the administrator.")
    assertNotContains(response, "INVALID_ARGUMENT")


def test_check_for_reports_fetches_them(
    client: Client, practice: Laboratory, owner: User, fake_laboratory: Running
) -> None:
    record = released_ferritin(fake_laboratory.laboratory)[0].sample.patient
    client.force_login(owner)
    response = client.post(reverse("practice:check_for_reports"))
    assert response["Location"] == reverse("practice:orders")
    assertContains(client.get(response["Location"]), "1 new lab report.")
    assert LabReport.objects.filter(order__test=OrderedTest.FERRITIN).exists()
    assert record.samples.get().orders.get(test=OrderedTest.FERRITIN).sent_at


def test_check_for_reports_on_a_patients_page_returns_to_it(
    client: Client, practice: Laboratory, owner: User, fake_laboratory: Running
) -> None:
    record = released_ferritin(fake_laboratory.laboratory)[0].sample.patient
    client.force_login(owner)
    page = reverse("practice:patient", kwargs={"pk": record.pk})
    check = reverse("practice:patient_check_for_reports", kwargs={"patient": record.pk})
    assertContains(client.get(page), f'action="{check}"')
    response = client.post(check)
    assert response["Location"] == page
    assertContains(client.get(page), "1 new lab report.")
    assert LabReport.objects.filter(order__test=OrderedTest.FERRITIN).exists()
    other = reverse("practice:patient_check_for_reports", kwargs={"patient": 0})
    assert client.post(other).status_code == 404


def test_without_a_laboratory_check_for_reports_asks_no_one(
    client: Client, owner: User
) -> None:
    """A practice with no laboratory has not been set up: its pages are the same,
    and checking asks no one and says nothing (add_laboratory sets it up)."""
    record = make_patient("Test Patient 1", RegisteredSex.FEMALE, 32)
    page = reverse("practice:patient", kwargs={"pk": record.pk})
    check = reverse("practice:patient_check_for_reports", kwargs={"patient": record.pk})
    client.force_login(owner)
    assertContains(client.get(reverse("practice:orders")), "Check for reports")
    assertContains(client.get(page), "Check for reports")
    for url, back in (
        (reverse("practice:check_for_reports"), reverse("practice:orders")),
        (check, page),
    ):
        response = client.post(url)
        assert response.status_code == 302
        assert response["Location"] == back
        assert not list(client.get(back).context["messages"])


def test_an_awaited_lab_report_says_how_to_fetch_it(
    client: Client, practice: Laboratory, owner: User
) -> None:
    # No timer fetches lab reports: only Check for reports does.
    record = make_patient("Test Patient 1", RegisteredSex.FEMALE, 32)
    client.force_login(owner)
    client.post(new_order_url(client, record))
    response = client.get(reverse("practice:patient", kwargs={"pk": record.pk}))
    assertContains(response, "<mark>Awaiting lab report</mark>")
    assertContains(response, "<small>Check for reports to fetch it.</small>")


def second_laboratory() -> Laboratory:
    """UZ Leuven, which the practice works with too: unreachable."""
    return Laboratory.objects.create(name="UZ Leuven", address="127.0.0.1:1")


def test_lab_orders_go_only_to_their_samples_laboratory(
    practice: Laboratory, owner: User, fake_laboratory: Running
) -> None:
    uz_leuven = second_laboratory()
    first = make_patient("Test Patient 1", RegisteredSex.FEMALE, 32)
    second = make_patient("Test Patient 2", RegisteredSex.FEMALE, 40)
    for record, laboratory in ((first, practice), (second, uz_leuven)):
        sample = record.collect_sample(laboratory=laboratory, now=NOW)
        suggest_ferritin_on(sample, NOW)
        sample.place_order(test=OrderedTest.FERRITIN, indication=None, now=NOW)
    assert grpc_client.send_pending_lab_orders(practice, now=NOW) == 1
    assert [sent.sample_id for sent in fake_laboratory.laboratory.lab_orders] == [
        latest_sample_id(first)
    ]
    unsent = Order.objects.get(sample__patient=second, test=OrderedTest.FERRITIN)
    assert unsent.sent_at is None


def test_a_laboratory_reports_only_on_the_samples_sent_to_it(
    practice: Laboratory, owner: User, fake_laboratory: Running
) -> None:
    """A lab report from AZ Diest for a sample that went to UZ Leuven is not
    stored, and stays unacknowledged there."""
    uz_leuven = second_laboratory()
    record = make_patient("Test Patient 1", RegisteredSex.FEMALE, 32)
    sample = record.collect_sample(laboratory=uz_leuven, now=NOW)
    suggest_ferritin_on(sample, NOW)
    placed = sample.place_order(test=OrderedTest.FERRITIN, indication=None, now=NOW)
    # AZ Diest releases a lab report on it anyway.
    report_id = fake_laboratory.laboratory.release(
        sample.sample_id.value, messages_pb2.TEST_FERRITIN, NOW
    )
    assert grpc_client.check_for_lab_reports(practice, now=NOW) == 0
    assert not LabReport.objects.filter(order=placed).exists()
    assert report_id not in fake_laboratory.laboratory.acknowledged


def test_check_for_reports_names_an_unreachable_laboratory_and_asks_the_others(
    client: Client, practice: Laboratory, owner: User, fake_laboratory: Running
) -> None:
    second_laboratory()
    released_ferritin(fake_laboratory.laboratory)
    client.force_login(owner)
    response = client.post(reverse("practice:check_for_reports"), follow=True)
    assertContains(response, "UZ Leuven could not be reached. Try again later.")
    assertContains(response, "1 new lab report.")
    assert LabReport.objects.filter(order__test=OrderedTest.FERRITIN).exists()


def test_add_laboratory_primary_makes_it_the_primary_one() -> None:
    call_command("add_laboratory", "UZ Leuven", "uz-leuven-grpc:8441")
    call_command("add_laboratory", "AZ Diest", "az-diest-grpc:8441", "--primary")
    primary = Laboratory.objects.primary()
    assert primary is not None
    assert primary.name == "AZ Diest"
    # Adding another without --primary keeps the primary one.
    call_command("add_laboratory", "UZ Leuven", "uz-leuven-grpc:9441")
    assert Laboratory.objects.primary() == primary


def test_add_laboratory_adds_it_then_changes_its_address() -> None:
    call_command("add_laboratory", "UZ Leuven", "uz-leuven-grpc:8441")
    call_command("add_laboratory", "UZ Leuven", "uz-leuven-grpc:9441")
    assert Laboratory.objects.get().address == "uz-leuven-grpc:9441"
