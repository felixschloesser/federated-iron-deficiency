"""Scenarios: the general practitioner's app sending lab orders and fetching lab
reports over gRPC (features/practice/messaging.feature), and its pages and
commands that do. The hospital is the stand-in tests/practice/fake_laboratory.py:
no hospital code, no hospital database."""

from datetime import UTC, datetime

import grpc
import pytest
from django.core.management import call_command
from django.test import Client
from django.urls import reverse
from pytest_bdd import given, parsers, scenarios, then, when
from pytest_django.asserts import assertContains, assertNotContains
from pytest_django.fixtures import Settings

from tests.conftest import World
from tests.practice.conftest import (
    Running,
    collect_and_order,
    make_general_practitioner,
    make_patient,
    suggest_ferritin_on,
)
from tests.practice.fake_laboratory import FakeLaboratory
from web.accounts.models import User
from web.messaging import messages_pb2
from web.practice import messaging
from web.practice.models import Laboratory, LabReport, Order, Patient
from web.vocabulary import ClinicalIndication, RegisteredSex
from web.vocabulary import Test as OrderedTest

NOW = datetime(2026, 10, 30, 10, 0, tzinfo=UTC)
# The stand-in serves from its own threads; the app's database stays in the test.
pytestmark = pytest.mark.django_db

scenarios("practice/messaging.feature")


def latest_sample_id(patient: Patient) -> str:
    """The sample ID of the patient's latest sample."""
    return patient.samples.latest("pk").sample_id


def stand_in(world: World) -> FakeLaboratory:
    laboratory: FakeLaboratory = world["stand_in"]
    return laboratory


@given(parsers.parse('hospital "{name}"'))
def hospital_ready(world: World, fake_laboratory: Running, name: str) -> None:
    world["stand_in"] = fake_laboratory.laboratory
    world["hospital"] = fake_laboratory.address


@given(
    parsers.parse(
        'general practitioner "{name}" of practice "{practice}",'
        ' working with "{hospital_name}"'
    )
)
def general_practitioner(
    world: World, settings: Settings, name: str, practice: str, hospital_name: str
) -> None:
    world["general_practitioners"][name] = make_general_practitioner(name)
    settings.PARTY_NAME = practice
    # The practice works with the hospital's laboratory.
    world["laboratory"] = Laboratory.objects.create(
        name=hospital_name, address=world["hospital"]
    )


@given(
    parsers.parse('"{name}" issued the practice certificate name "{certificate_name}"')
)
def issued_certificate_name(
    settings: Settings, name: str, certificate_name: str
) -> None:
    settings.PRACTICE_CERTIFICATE_NAME = certificate_name


@given(
    parsers.parse(
        'patient "{patient}" of "{owner}", registered sex {sex}, aged {age:d}'
    )
)
def patient(world: World, patient: str, owner: str, sex: str, age: int) -> None:
    world["patients"][patient] = make_patient(patient, RegisteredSex(sex), age)


def order(
    world: World, patient: str, test: OrderedTest, indication: str | None
) -> Order:
    choice = (
        {choice.label.lower(): choice for choice in ClinicalIndication}[indication]
        if indication
        else None
    )
    placed: Order = collect_and_order(
        patient=world["patients"][patient], test=test, indication=choice, now=NOW
    )
    world["order"] = placed
    return placed


@when(
    parsers.re(
        r'"(?P<owner>[^"]+)" orders a CBC for "(?P<patient>[^"]+)"'
        r" with indication (?P<indication>.+)$"
    )
)
def orders_cbc(world: World, owner: str, patient: str, indication: str) -> None:
    order(world, patient, OrderedTest.CBC, indication)
    messaging.send_pending_lab_orders(world["laboratory"], now=NOW)


@then(parsers.parse('"{name}" received a lab order for the sample of "{patient}"'))
def received_lab_order(world: World, name: str, patient: str) -> None:
    sample_id = latest_sample_id(world["patients"][patient])
    assert [sent.sample_id for sent in stand_in(world).lab_orders] == [sample_id]


@then(
    parsers.parse(
        "the lab order holds sample ID, test, whether its indication is screened,"
        ' registered sex and age, from certificate name "{certificate_name}"'
    )
)
def lab_order_holds(world: World, certificate_name: str) -> None:
    (sent,) = stand_in(world).lab_orders
    placed = world["order"]
    assert sent.sample_id == placed.sample.sample_id
    assert sent.test == messages_pb2.TEST_CBC
    assert (
        sent.screened_indication is ClinicalIndication(placed.indication).is_screened()
    )
    assert sent.registered_sex == messages_pb2.REGISTERED_SEX_FEMALE
    assert sent.age == placed.age
    assert sent.ordered_at.ToDatetime(tzinfo=UTC) == placed.ordered_at
    # The practice by the certificate name the hospital issued; no general practitioner.
    assert sent.certificate_name == certificate_name


@then(parsers.parse("the lab order says its indication is {screened}"))
def says_screened(world: World, screened: str) -> None:
    (sent,) = stand_in(world).lab_orders
    assert sent.screened_indication is (screened == "screened")


@given(parsers.parse('"{name}" released a lab report for the sample of "{patient}"'))
def released(world: World, name: str, patient: str) -> None:
    placed = order(world, patient, OrderedTest.FERRITIN, None)
    world["report_id"] = stand_in(world).release(
        placed.sample.sample_id, messages_pb2.TEST_FERRITIN, NOW
    )


@given(
    parsers.parse(
        '"{name}" released a CBC lab report with ferritin suggested'
        ' for the sample of "{patient}"'
    )
)
def released_suggested(world: World, name: str, patient: str) -> None:
    placed = order(world, patient, OrderedTest.CBC, "unexplained fatigue")
    world["report_id"] = stand_in(world).release(
        placed.sample.sample_id,
        messages_pb2.TEST_CBC,
        NOW,
        ferritin_suggested=True,
    )


@given(
    parsers.parse('"{name}" released a lab report for a sample "{owner}" never ordered')
)
def released_unknown(world: World, name: str, owner: str) -> None:
    world["stranger_id"] = stand_in(world).release(
        "999999-1", messages_pb2.TEST_FERRITIN, NOW
    )


@when("the general practitioner's app checks for lab reports")
@given("the general practitioner's app checked for lab reports")
def checks(world: World) -> None:
    messaging.check_for_lab_reports(world["laboratory"], now=NOW)


@then(parsers.parse('"{owner}" has the lab report of "{patient}"'))
def has_lab_report(world: World, owner: str, patient: str) -> None:
    assert LabReport.objects.filter(
        order=world["order"], order__sample__patient=world["patients"][patient]
    ).exists()


@then(parsers.parse('"{owner}" has one lab report of "{patient}"'))
def has_one_lab_report(world: World, owner: str, patient: str) -> None:
    # The ferritin's; the CBC's lab report that suggested it came with the setup.
    reports = LabReport.objects.filter(
        order__sample__patient=world["patients"][patient],
        order__test=OrderedTest.FERRITIN,
    )
    assert reports.count() == 1


@then(
    parsers.parse('the lab report of "{patient}" has ferritin suggested at "{owner}"')
)
def has_ferritin_suggested(world: World, patient: str, owner: str) -> None:
    report = LabReport.objects.get(order=world["order"])
    assert report.ferritin_suggested is True


@then(parsers.parse('the lab report of "{patient}" is no longer new at "{name}"'))
def no_longer_new(world: World, patient: str, name: str) -> None:
    assert world["report_id"] in stand_in(world).acknowledged


@then(
    parsers.parse(
        'the lab report for the sample never ordered is still new at "{name}"'
    )
)
def stranger_still_new(world: World, name: str) -> None:
    assert world["stranger_id"] not in stand_in(world).acknowledged


# The general practitioner's app in use: its views and command talk to the endpoint.


@pytest.fixture
def practice(settings: Settings, fake_laboratory: Running) -> Laboratory:
    """Practice "De Ceder", working with the laboratory "AZ Diest"."""
    settings.PARTY_NAME = "De Ceder"
    return Laboratory.objects.create(name="AZ Diest", address=fake_laboratory.address)


@pytest.fixture
def owner() -> User:
    return make_general_practitioner("Dr. Demo A")


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


def released_ferritin(laboratory: FakeLaboratory) -> Patient:
    """A patient whose ferritin the hospital has analysed and released."""
    record = make_patient("Test Patient 1", RegisteredSex.FEMALE, 32)
    placed = collect_and_order(
        patient=record, test=OrderedTest.FERRITIN, indication=None, now=NOW
    )
    laboratory.release(placed.sample.sample_id, messages_pb2.TEST_FERRITIN, NOW)
    return record


def test_check_for_reports_fetches_them(
    client: Client, practice: Laboratory, owner: User, fake_laboratory: Running
) -> None:
    record = released_ferritin(fake_laboratory.laboratory)
    client.force_login(owner)
    response = client.post(reverse("practice:check_for_reports"))
    assert response["Location"] == reverse("practice:orders")
    assertContains(client.get(response["Location"]), "1 new lab report.")
    assert LabReport.objects.filter(order__test=OrderedTest.FERRITIN).exists()
    assert record.samples.get().orders.get(test=OrderedTest.FERRITIN).sent_at


def test_check_for_reports_on_a_patients_page_returns_to_it(
    client: Client, practice: Laboratory, owner: User, fake_laboratory: Running
) -> None:
    record = released_ferritin(fake_laboratory.laboratory)
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


def test_check_for_reports_is_offered_only_with_a_laboratory_to_ask(
    client: Client, practice: Laboratory, owner: User
) -> None:
    record = make_patient("Test Patient 1", RegisteredSex.FEMALE, 32)
    page = reverse("practice:patient", kwargs={"pk": record.pk})
    check = reverse("practice:patient_check_for_reports", kwargs={"patient": record.pk})
    client.force_login(owner)
    assertContains(client.get(reverse("practice:orders")), "Check for reports")
    assertContains(client.get(page), "Check for reports")
    Laboratory.objects.all().delete()
    assertNotContains(client.get(reverse("practice:orders")), "Check for reports")
    assertNotContains(client.get(page), "Check for reports")
    assert client.post(reverse("practice:check_for_reports")).status_code == 404
    assert client.post(check).status_code == 404


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
    assert messaging.send_pending_lab_orders(practice, now=NOW) == 1
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
        sample.sample_id, messages_pb2.TEST_FERRITIN, NOW
    )
    assert messaging.check_for_lab_reports(practice, now=NOW) == 0
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
    call_command("add_laboratory", "UZ Leuven", "uz-leuven-messaging:8441")
    call_command("add_laboratory", "AZ Diest", "az-diest-messaging:8441", "--primary")
    primary = Laboratory.objects.primary()
    assert primary is not None
    assert primary.name == "AZ Diest"
    # Adding another without --primary keeps the primary one.
    call_command("add_laboratory", "UZ Leuven", "uz-leuven-messaging:9441")
    assert Laboratory.objects.primary() == primary


def test_add_laboratory_adds_it_then_changes_its_address() -> None:
    call_command("add_laboratory", "UZ Leuven", "uz-leuven-messaging:8441")
    call_command("add_laboratory", "UZ Leuven", "uz-leuven-messaging:9441")
    assert Laboratory.objects.get().address == "uz-leuven-messaging:9441"
