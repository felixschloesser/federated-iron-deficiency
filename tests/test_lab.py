"""Scenarios: receiving and analysing samples (features/lab.feature), and the
lab never seeing a patient's name (features/access.feature)."""

from dataclasses import fields
from datetime import UTC, datetime

from django.core.exceptions import ValidationError
from pytest_bdd import given, parsers, scenario, scenarios, then, when

from iron_deficiency.dataset import CBC_VARS
from tests.conftest import World
from web.lab import queries, services
from web.practice import services as practice_services
from web.practice.models import ClinicalIndication
from web.practice.models import Test as OrderedTest

NOW = datetime(2026, 10, 29, 10, 0, tzinfo=UTC)
TESTS = {"CBC": OrderedTest.CBC, "ferritin": OrderedTest.FERRITIN}

scenarios("lab.feature")


@scenario("access.feature", "The lab never sees a patient's name")
def test_the_lab_never_sees_a_patients_name() -> None:
    pass


def place(world: World, test: str, patient: str) -> None:
    ordered = TESTS[test]
    indication = (
        ClinicalIndication.NON_SPECIFIC_COMPLAINT
        if ordered.takes_indication()
        else None
    )
    owner = world["patients"][patient].general_practitioner
    world["order"] = practice_services.place_order(
        general_practitioner=owner,
        patient=world["patients"][patient],
        test=ordered,
        indication=indication,
        now=NOW,
    )


@given(
    parsers.parse('"{patient}" has NHANES CBC values and ferritin {ferritin:g} ng/mL')
)
def nhanes_values(world: World, patient: str, ferritin: float) -> None:
    participant = world["patients"][patient].participant
    participant.cbc = {var: float(index) for index, var in enumerate(CBC_VARS, 1)}
    participant.ferritin = ferritin
    participant.save()


@given(parsers.parse('patient "{patient}" of "{owner}" without NHANES ferritin'))
def patient_without_ferritin(world: World, patient: str, owner: str) -> None:
    from tests.conftest import make_patient
    from web.practice.models import RegisteredSex

    world["patients"][patient] = make_patient(
        world["general_practitioners"][owner], patient, RegisteredSex.FEMALE, 30
    )


@given(parsers.re(r'a (?P<test>CBC|ferritin) order for "(?P<patient>[^"]+)"$'))
def an_order(world: World, test: str, patient: str) -> None:
    place(world, test, patient)


@given(
    parsers.re(
        r'a (?P<test>CBC|ferritin) order for "(?P<patient>[^"]+)" that has been received'
    )
)
def a_received_order(world: World, test: str, patient: str) -> None:
    place(world, test, patient)
    world["sample"] = services.receive(order=world["order"], now=NOW)


@given(parsers.re(r'a received (?P<test>CBC|ferritin) sample for "(?P<patient>[^"]+)"'))
def a_received_sample(world: World, test: str, patient: str) -> None:
    a_received_order(world, test, patient)


@given(
    parsers.re(r'an analysed (?P<test>CBC|ferritin) sample for "(?P<patient>[^"]+)"')
)
def an_analysed_sample(world: World, test: str, patient: str) -> None:
    a_received_order(world, test, patient)
    world["sample"] = services.run_analyser(sample=world["sample"], now=NOW)


@when("laboratory staff receive the order")
def receive(world: World) -> None:
    try:
        world["sample"] = services.receive(order=world["order"], now=NOW)
    except ValidationError as error:
        world["error"] = error


@when("laboratory staff run the analyser")
def run_analyser(world: World) -> None:
    try:
        world["sample"] = services.run_analyser(sample=world["sample"], now=NOW)
    except ValidationError as error:
        world["error"] = error


@then("the order has a sample with a sample ID, received at the current time")
def order_has_sample(world: World) -> None:
    sample = world["order"].sample
    assert sample.sample_id
    assert sample.received_at == NOW


@then(parsers.parse('{action} is refused with code "{code}"'))
def refused(world: World, action: str, code: str) -> None:
    assert world["error"].code == code


@then(parsers.parse('the sample has the 13 NHANES CBC values of "{patient}"'))
def sample_has_cbc(world: World, patient: str) -> None:
    sample = world["sample"]
    assert sample.results == world["patients"][patient].participant.cbc
    assert len(sample.results) == 13
    assert sample.analysed_at == NOW


@then("running the analyser is not offered for the order")
def analyser_not_offered(world: World) -> None:
    order = world["order"]
    assert order.pk not in [row.order for row in queries.samples_to_analyse()]
    assert order.pk in [row.order for row in queries.orders_to_receive()]


@then(parsers.parse("the sample has ferritin {ferritin:g} ng/mL"))
def sample_has_ferritin(world: World, ferritin: float) -> None:
    assert world["sample"].ferritin == ferritin


@then("the sample's ferritin is not available in the demo data")
def ferritin_not_available(world: World) -> None:
    assert world["sample"].analysed_at == NOW
    assert world["sample"].ferritin is None


@then(
    "the lab's samples hold sample ID, ordering general practitioner, registered sex,"
    " age, test, indication and results"
)
def lab_rows_hold(world: World) -> None:
    (row,) = queries.samples_to_analyse()
    assert row.sample_id == world["sample"].sample_id
    assert row.general_practitioner == "Dr. Demo A"
    assert row.registered_sex == "Female"
    assert row.test == "CBC"


@then("no lab query returns the patient's name")
def no_patient_name(world: World) -> None:
    rows = [
        *queries.orders_to_receive(),
        *queries.samples_to_analyse(),
        *queries.samples_analysed(),
    ]
    for row in rows:
        assert not any("patient" in field.name for field in fields(row))
        assert "Test Patient" not in repr(row)
