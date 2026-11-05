"""Scenarios: lab orders and lab reports between the general practitioner's app
and the hospital, over gRPC (features/messaging.feature)."""

from collections.abc import Iterator
from datetime import UTC, datetime

import grpc
import pytest
from django.core.management import call_command
from django.test import Client, override_settings
from django.urls import reverse
from pytest_bdd import given, parsers, scenarios, then, when
from pytest_django.asserts import assertContains, assertNotContains
from pytest_django.fixtures import Settings

from tests.conftest import (
    World,
    collect_and_order,
    make_general_practitioner,
    make_patient,
    suggest_ferritin_on,
)
from web.lab.messaging import serve
from web.lab.models import LabOrder, Sample
from web.messaging import messages_pb2
from web.nhanes.models import Participant
from web.practice import messaging
from web.practice.models import (
    GeneralPractitioner,
    Laboratory,
    LabReport,
    Order,
    Patient,
)
from web.practice.models import Sample as PracticeSample
from web.vocabulary import ClinicalIndication, RegisteredSex
from web.vocabulary import Test as OrderedTest

NOW = datetime(2026, 10, 30, 10, 0, tzinfo=UTC)
# The server runs in its own threads, so the test may not hold a transaction.
pytestmark = pytest.mark.django_db(transaction=True)


def latest_sample_id(patient: Patient) -> str:
    """The sample ID of the patient's latest sample."""
    return patient.samples.latest("pk").sample_id


scenarios("messaging.feature")


@pytest.fixture
def hospital() -> Iterator[str]:
    """The hospital's endpoint, running; its address."""
    server, port = serve("127.0.0.1:0")
    yield f"127.0.0.1:{port}"
    server.stop(grace=None)


@given(parsers.parse('hospital "{name}"'))
def hospital_ready(world: World, hospital: str, name: str) -> None:
    world["hospital"] = hospital


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
    # The practice works with the hospital's laboratory (R22).
    world["laboratory"] = Laboratory.objects.create(
        name=hospital_name, address=world["hospital"]
    )


@given(
    parsers.parse(
        'patient "{patient}" of "{owner}", registered sex {sex}, aged {age:d}'
    )
)
def patient(world: World, patient: str, owner: str, sex: str, age: int) -> None:
    world["patients"][patient] = make_patient(
        world["general_practitioners"][owner], patient, RegisteredSex(sex), age
    )


def order(
    world: World, patient: str, test: OrderedTest, indication: str | None
) -> Order:
    record = world["patients"][patient]
    choice = (
        {c.label.lower(): c for c in ClinicalIndication}[indication]
        if indication
        else None
    )
    placed: Order = collect_and_order(
        general_practitioner=record.general_practitioner,
        patient=record,
        test=test,
        indication=choice,
        now=NOW,
    )
    world["order"] = placed
    return placed


@when(
    parsers.re(
        r'"(?P<owner>[^"]+)" orders a CBC for "(?P<patient>[^"]+)"'
        r" with indication (?P<indication>.+)$"
    )
)
@given(
    parsers.re(
        r'"(?P<owner>[^"]+)" ordered a CBC for "(?P<patient>[^"]+)"'
        r" with indication (?P<indication>.+)$"
    )
)
def orders_cbc(world: World, owner: str, patient: str, indication: str) -> None:
    order(world, patient, OrderedTest.CBC, indication)
    messaging.send_pending_lab_orders(world["laboratory"], now=NOW)


@when("the same lab order is sent again")
def send_again(world: World) -> None:
    messaging.send_lab_order(world["order"], world["laboratory"])


@when(parsers.parse('a lab order that names no practice is sent to "{name}"'))
def sends_without_practice(world: World) -> None:
    unsent = order(world, "Test Patient 1", OrderedTest.CBC, "other")
    with override_settings(PARTY_NAME=""):
        try:
            messaging.send_lab_order(unsent, world["laboratory"])
        except grpc.RpcError as error:
            world["refused"] = error


@given(parsers.parse('"{name}" released a lab report for the sample of "{patient}"'))
def released(world: World, name: str, patient: str) -> None:
    order(world, patient, OrderedTest.FERRITIN, None)
    messaging.send_pending_lab_orders(world["laboratory"], now=NOW)
    lab_order = LabOrder.objects.select_related("sample").get(
        sample__sample_id=latest_sample_id(world["patients"][patient])
    )
    lab_order.run_analyser(directory=None, now=NOW)


@given(
    parsers.parse(
        '"{name}" released a CBC lab report with ferritin suggested'
        ' for the sample of "{patient}"'
    )
)
def released_suggested(world: World, name: str, patient: str) -> None:
    from web.lab.models import ScreeningResult

    order(world, patient, OrderedTest.CBC, "unexplained fatigue")
    messaging.send_pending_lab_orders(world["laboratory"], now=NOW)
    lab_order = LabOrder.objects.select_related("sample").get(
        sample__sample_id=latest_sample_id(world["patients"][patient])
    )
    lab_order.run_analyser(directory=None, now=NOW)
    # As the deployed model would have decided (features/screening.feature).
    LabOrder.objects.filter(pk=lab_order.pk).update(
        screening_result=ScreeningResult.FERRITIN_SUGGESTED, not_screened_reason=None
    )


@then(
    parsers.parse('the lab report of "{patient}" has ferritin suggested at "{owner}"')
)
def has_ferritin_suggested(world: World, patient: str, owner: str) -> None:
    report = LabReport.objects.get(order__sample__patient=world["patients"][patient])
    assert report.ferritin_suggested is True


@when("the general practitioner's app checks for lab reports")
@given("the general practitioner's app checked for lab reports")
def checks(world: World) -> None:
    messaging.check_for_lab_reports(world["laboratory"], now=NOW)


@then(parsers.parse('"{name}" has a lab order for the sample of "{patient}"'))
def has_lab_order(world: World, name: str, patient: str) -> None:
    sample_id = latest_sample_id(world["patients"][patient])
    assert LabOrder.objects.filter(sample__sample_id=sample_id).exists()


@then(parsers.parse('"{name}" has one lab order for the sample of "{patient}"'))
def has_one_lab_order(world: World, name: str, patient: str) -> None:
    sample_id = latest_sample_id(world["patients"][patient])
    assert LabOrder.objects.filter(sample__sample_id=sample_id).count() == 1


@then(
    parsers.parse(
        "the lab order holds sample ID, test, whether its indication is screened,"
        ' registered sex and age, from practice "{practice}"'
    )
)
def lab_order_holds(world: World, practice: str) -> None:
    lab_order = LabOrder.objects.select_related("sample").get()
    placed = world["order"]
    assert lab_order.sample.sample_id == placed.sample.sample_id
    screened = ClinicalIndication(placed.indication).is_screened()
    assert (lab_order.test, lab_order.screened_indication) == (placed.test, screened)
    assert (lab_order.registered_sex, lab_order.age) == (
        placed.registered_sex,
        placed.age,
    )
    # The practice by the name it sent; no general practitioner.
    assert lab_order.sample.practice == practice


@then("it is refused as practice required")
def refused_practice_required(world: World) -> None:
    assert world["refused"].code() == grpc.StatusCode.INVALID_ARGUMENT
    assert world["refused"].details() == "practice_required"


@then(parsers.parse('"{name}" has no lab order'))
def no_lab_order(world: World, name: str) -> None:
    assert not LabOrder.objects.exists()


@then(parsers.parse('"{owner}" has the lab report of "{patient}"'))
def has_lab_report(world: World, owner: str, patient: str) -> None:
    assert LabReport.objects.filter(
        order__sample__patient=world["patients"][patient]
    ).exists()


@then(parsers.parse('"{owner}" has one lab report of "{patient}"'))
def has_one_lab_report(world: World, owner: str, patient: str) -> None:
    # The ferritin's; the CBC's lab report that suggested it came with the setup.
    reports = LabReport.objects.filter(
        order__sample__patient=world["patients"][patient],
        order__test=OrderedTest.FERRITIN,
    )
    assert reports.count() == 1


@given(parsers.parse('the app of another practice "{practice}"'))
def other_app(world: World, practice: str) -> None:
    world["other"] = practice


@when("the other app checks for lab reports")
def other_checks(world: World) -> None:
    with messaging.open_laboratory(world["laboratory"]) as laboratory:
        world["received"] = laboratory.FetchNewLabReports(
            messages_pb2.FetchLabReports(practice=world["other"]), timeout=10
        )


@then("it receives no lab reports")
def receives_none(world: World) -> None:
    assert list(world["received"].reports) == []


def lab_order_of(world: World, patient: str) -> LabOrder:
    return LabOrder.objects.get(
        sample__sample_id=latest_sample_id(world["patients"][patient]),
        test=world["order"].test,
    )


@then(parsers.parse('the lab report of "{patient}" is still new at "{name}"'))
def still_new(world: World, patient: str, name: str) -> None:
    assert lab_order_of(world, patient).report_acknowledged_at is None


@then(parsers.parse('the lab report of "{patient}" is no longer new at "{name}"'))
def no_longer_new(world: World, patient: str, name: str) -> None:
    assert lab_order_of(world, patient).report_acknowledged_at is not None


@when(parsers.parse('the other app acknowledges the lab report of "{patient}"'))
def other_acknowledges(world: World, patient: str) -> None:
    with messaging.open_laboratory(world["laboratory"]) as laboratory:
        report_id = str(lab_order_of(world, patient).pk)
        laboratory.AcknowledgeLabReports(
            messages_pb2.Acknowledgement(
                practice=world["other"], report_ids=[report_id]
            ),
            timeout=10,
        )


@when(
    parsers.parse('the other app sends a lab order with the sample ID of "{patient}"')
)
def other_sends(world: World, patient: str) -> None:
    with override_settings(PARTY_NAME=world["other"]):
        messaging.send_lab_order(world["order"], world["laboratory"])


@then(parsers.parse('"{name}" has two samples with the sample ID of "{patient}"'))
def two_samples(world: World, name: str, patient: str) -> None:
    sample_id = latest_sample_id(world["patients"][patient])
    assert Sample.objects.filter(sample_id=sample_id).count() == 2


@given(
    parsers.parse('"{name}" released a lab report for a sample "{owner}" never ordered')
)
def released_unknown(world: World, name: str, owner: str) -> None:
    """A lab order from this app the app itself has no order for."""
    Participant.objects.create(seqn=999999, cbc={})
    stranger = Order(
        sample=PracticeSample(
            patient=world["patients"]["Test Patient 1"],
            sample_id="999999",
            collected_at=NOW,
        ),
        test=OrderedTest.FERRITIN,
        indication=None,
        registered_sex=RegisteredSex.FEMALE,
        age=30,
        ordered_at=NOW,
    )
    messaging.send_lab_order(stranger, world["laboratory"])
    lab_order = LabOrder.objects.select_related("sample").get(
        sample__sample_id="999999"
    )
    lab_order.run_analyser(directory=None, now=NOW)


@then(
    "the lab order has no field for a patient's name or blood values,"
    " only the practice's name"
)
def lab_order_fields() -> None:
    fields = {field.name for field in messages_pb2.LabOrder.DESCRIPTOR.fields}
    assert fields == {
        "practice",
        "sample_id",
        "test",
        "screened_indication",
        "registered_sex",
        "age",
        "ordered_at",
    }


@then(
    "the lab report says only whether ferritin is suggested, nothing else of screening"
)
def lab_report_fields() -> None:
    fields = {field.name for field in messages_pb2.LabReport.DESCRIPTOR.fields}
    assert fields == {
        "report_id",
        "sample_id",
        "test",
        "results",
        "ferritin_suggested",
        "released_at",
    }


# The general practitioner's app in use: its views and command talk to the endpoint.


@pytest.fixture
def practice(settings: Settings, hospital: str) -> Laboratory:
    """Practice "De Ceder", working with the hospital's laboratory "AZ Diest"."""
    settings.PARTY_NAME = "De Ceder"
    return Laboratory.objects.create(name="AZ Diest", address=hospital)


@pytest.fixture
def owner() -> GeneralPractitioner:
    return make_general_practitioner("Dr. Demo A")


def new_order_url(client: Client, record: Patient) -> str:
    """Collect a sample from the patient; the ferritin order page on it, beside
    a CBC lab report suggesting ferritin (R11)."""
    client.post(reverse("practice:collect_sample", kwargs={"patient": record.pk}))
    suggest_ferritin_on(record.samples.latest("pk"), NOW)
    return reverse(
        "practice:new_order",
        kwargs={
            "patient": record.pk,
            "sample": record.samples.latest("pk").pk,
            "test": OrderedTest.FERRITIN,
        },
    )


def test_placing_an_order_sends_its_lab_order(
    client: Client, practice: Laboratory, owner: GeneralPractitioner
) -> None:
    record = make_patient(owner, "Test Patient 1", RegisteredSex.FEMALE, 32)
    client.force_login(owner.user)
    client.post(new_order_url(client, record))
    assert LabOrder.objects.filter(sample__sample_id=latest_sample_id(record)).exists()
    assert Order.objects.get(test=OrderedTest.FERRITIN).sent_at is not None


def test_an_unreachable_hospital_gets_the_order_with_the_next_check(
    client: Client, settings: Settings, practice: Laboratory, owner: GeneralPractitioner
) -> None:
    Laboratory.objects.update(address="127.0.0.1:1")
    record = make_patient(owner, "Test Patient 1", RegisteredSex.FEMALE, 32)
    client.force_login(owner.user)
    response = client.post(new_order_url(client, record), follow=True)
    assertContains(response, "Ferritin ordered on sample")
    assertContains(
        response, "AZ Diest could not be reached, so the lab order is not sent yet."
    )
    assertNotContains(response, "next check")
    assert Order.objects.get(test=OrderedTest.FERRITIN).sent_at is None


def test_a_hospital_refusing_a_lab_order_is_not_called_unreachable(
    client: Client, practice: Laboratory, owner: GeneralPractitioner
) -> None:
    """A message the hospital's form rejects (INVALID_ARGUMENT) is a fault to
    report, not a network problem to wait out."""
    record = make_patient(owner, "Test Patient 1", RegisteredSex.FEMALE, 32)
    sample = record.samples.create(
        sample_id="x" * 25, collected_at=NOW, laboratory=Laboratory.objects.get()
    )
    suggest_ferritin_on(sample, NOW)
    owner.place_order(
        sample=sample, test=OrderedTest.FERRITIN, indication=None, now=NOW
    )
    client.force_login(owner.user)
    response = client.post(reverse("practice:check_for_reports"), follow=True)
    assertNotContains(response, "could not be reached")
    assertContains(response, "AZ Diest refused a message. Tell the administrator.")
    assertNotContains(response, "INVALID_ARGUMENT")


def released_ferritin(owner: GeneralPractitioner) -> Patient:
    """A patient whose ferritin the hospital has analysed and released."""
    record = make_patient(owner, "Test Patient 1", RegisteredSex.FEMALE, 32)
    collect_and_order(
        general_practitioner=owner,
        patient=record,
        test=OrderedTest.FERRITIN,
        indication=None,
        now=NOW,
    )
    laboratory = Laboratory.objects.get(name="AZ Diest")
    messaging.send_pending_lab_orders(laboratory, now=NOW)
    lab_order = LabOrder.objects.select_related("sample").get()
    lab_order.run_analyser(directory=None, now=NOW)
    return record


def test_check_for_reports_fetches_them(
    client: Client, practice: Laboratory, owner: GeneralPractitioner
) -> None:
    record = released_ferritin(owner)
    client.force_login(owner.user)
    response = client.post(reverse("practice:check_for_reports"))
    assert response["Location"] == reverse("practice:orders")
    assertContains(client.get(response["Location"]), "1 new lab report.")
    assert LabReport.objects.filter(order__sample__patient=record).exists()


def test_check_for_reports_on_a_patients_page_returns_to_it(
    client: Client, practice: Laboratory, owner: GeneralPractitioner
) -> None:
    record = released_ferritin(owner)
    client.force_login(owner.user)
    page = reverse("practice:patient", kwargs={"pk": record.pk})
    check = reverse("practice:patient_check_for_reports", kwargs={"patient": record.pk})
    assertContains(client.get(page), f'action="{check}"')
    response = client.post(check)
    assert response["Location"] == page
    assertContains(client.get(page), "1 new lab report.")
    assert LabReport.objects.filter(order__sample__patient=record).exists()
    other = reverse("practice:patient_check_for_reports", kwargs={"patient": 0})
    assert client.post(other).status_code == 404


def test_check_for_reports_is_offered_only_with_a_laboratory_to_ask(
    client: Client, practice: Laboratory, owner: GeneralPractitioner
) -> None:
    record = make_patient(owner, "Test Patient 1", RegisteredSex.FEMALE, 32)
    page = reverse("practice:patient", kwargs={"pk": record.pk})
    check = reverse("practice:patient_check_for_reports", kwargs={"patient": record.pk})
    client.force_login(owner.user)
    assertContains(client.get(reverse("practice:orders")), "Check for reports")
    assertContains(client.get(page), "Check for reports")
    Laboratory.objects.all().delete()
    assertNotContains(client.get(reverse("practice:orders")), "Check for reports")
    assertNotContains(client.get(page), "Check for reports")
    assert client.post(reverse("practice:check_for_reports")).status_code == 404
    assert client.post(check).status_code == 404


def test_an_awaited_lab_report_says_how_to_fetch_it(
    client: Client, settings: Settings, practice: Laboratory, owner: GeneralPractitioner
) -> None:
    # No timer fetches lab reports: only Check for reports does (R23).
    record = make_patient(owner, "Test Patient 1", RegisteredSex.FEMALE, 32)
    client.force_login(owner.user)
    client.post(new_order_url(client, record))
    page = reverse("practice:patient", kwargs={"pk": record.pk})
    response = client.get(page)
    assertContains(response, "<mark>Awaiting lab report</mark>")
    assertContains(
        response,
        "<small>Check for reports to fetch it.</small>",
    )


@then(parsers.parse("the lab order says its indication is {screened}"))
def says_screened(world: World, screened: str) -> None:
    lab_order = LabOrder.objects.get()
    assert lab_order.screened_indication is (screened == "screened")


@then("no lab order names a clinical indication")
def names_no_indication() -> None:
    # Neither the message (DF23) nor what the hospital stores (DS8) has a field
    # for it: the laboratory never learns why a CBC was ordered.
    from web.messaging import messages_pb2

    assert "indication" not in messages_pb2.LabOrder.DESCRIPTOR.fields_by_name
    stored = {field.name for field in LabOrder._meta.get_fields()}
    assert "indication" not in stored


def second_laboratory() -> Laboratory:
    """UZ Leuven, which the practice works with too: unreachable."""
    return Laboratory.objects.create(name="UZ Leuven", address="127.0.0.1:1")


def test_lab_orders_go_only_to_their_samples_laboratory(
    practice: Laboratory, owner: GeneralPractitioner
) -> None:
    az_diest = Laboratory.objects.get(name="AZ Diest")
    uz_leuven = second_laboratory()
    first = make_patient(owner, "Test Patient 1", RegisteredSex.FEMALE, 32)
    second = make_patient(owner, "Test Patient 2", RegisteredSex.FEMALE, 40)
    for record, laboratory in ((first, az_diest), (second, uz_leuven)):
        sample = owner.collect_sample(patient=record, laboratory=laboratory, now=NOW)
        suggest_ferritin_on(sample, NOW)
        owner.place_order(
            sample=sample, test=OrderedTest.FERRITIN, indication=None, now=NOW
        )
    assert messaging.send_pending_lab_orders(az_diest, now=NOW) == 1
    assert [lab_order.sample.sample_id for lab_order in LabOrder.objects.all()] == [
        latest_sample_id(first)
    ]
    unsent = Order.objects.get(sample__patient=second, test=OrderedTest.FERRITIN)
    assert unsent.sent_at is None


def test_a_laboratory_reports_only_on_the_samples_sent_to_it(
    practice: Laboratory, owner: GeneralPractitioner
) -> None:
    """A lab report from AZ Diest for a sample that went to UZ Leuven is not
    stored, and stays unacknowledged there."""
    az_diest = Laboratory.objects.get(name="AZ Diest")
    uz_leuven = second_laboratory()
    record = make_patient(owner, "Test Patient 1", RegisteredSex.FEMALE, 32)
    sample = owner.collect_sample(patient=record, laboratory=uz_leuven, now=NOW)
    suggest_ferritin_on(sample, NOW)
    placed = owner.place_order(
        sample=sample, test=OrderedTest.FERRITIN, indication=None, now=NOW
    )
    # AZ Diest holds the lab order anyway, and releases a report on it.
    messaging.send_lab_order(placed, az_diest)
    LabOrder.objects.select_related("sample").get().run_analyser(
        directory=None, now=NOW
    )
    assert messaging.check_for_lab_reports(az_diest, now=NOW) == 0
    assert not LabReport.objects.filter(order=placed).exists()


def test_check_for_reports_names_an_unreachable_laboratory_and_asks_the_others(
    client: Client,
    practice: Laboratory,
    owner: GeneralPractitioner,
) -> None:
    second_laboratory()
    record = released_ferritin(owner)
    client.force_login(owner.user)
    response = client.post(reverse("practice:check_for_reports"), follow=True)
    assertContains(response, "UZ Leuven could not be reached. Try again later.")
    assertContains(response, "1 new lab report.")
    assert LabReport.objects.filter(order__sample__patient=record).exists()


def test_add_laboratory_primary_makes_it_the_primary_one() -> None:
    call_command("add_laboratory", "UZ Leuven", "uz-leuven-lab-orders:8441")
    call_command("add_laboratory", "AZ Diest", "az-diest-lab-orders:8441", "--primary")
    primary = Laboratory.objects.primary()
    assert primary is not None
    assert primary.name == "AZ Diest"
    # Adding another without --primary keeps the primary one.
    call_command("add_laboratory", "UZ Leuven", "uz-leuven-lab-orders:9441")
    assert Laboratory.objects.primary() == primary


def test_add_laboratory_adds_it_then_changes_its_address() -> None:
    call_command("add_laboratory", "UZ Leuven", "uz-leuven-lab-orders:8441")
    call_command("add_laboratory", "UZ Leuven", "uz-leuven-lab-orders:9441")
    assert Laboratory.objects.get().address == "uz-leuven-lab-orders:9441"
