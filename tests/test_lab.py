"""Scenarios: receiving and analysing samples (features/lab.feature), and the
lab never seeing a patient's name (features/access.feature)."""

from datetime import UTC, datetime

import pytest
from django.core.exceptions import ValidationError
from pytest_bdd import given, parsers, scenario, scenarios, then, when

from iron_deficiency.dataset import CBC_VARS
from tests.conftest import World
from web.lab import queries, services
from web.lab.models import LabOrder, Sample
from web.nhanes.models import Participant
from web.practice import services as practice_services
from web.practice.models import Patient
from web.vocabulary import ClinicalIndication
from web.vocabulary import Test as OrderedTest

NOW = datetime(2026, 10, 29, 10, 0, tzinfo=UTC)
TESTS = {"CBC": OrderedTest.CBC, "ferritin": OrderedTest.FERRITIN}
pytestmark = pytest.mark.django_db

scenarios("lab.feature")


@scenario("access.feature", "The lab never sees a patient's name")
def test_the_lab_never_sees_a_patients_name() -> None:
    pass


def tube(patient: Patient) -> Participant:
    """What the patient's tube would measure, at the hospital's analyser stand-in."""
    return Participant.objects.get(seqn=int(patient.sample_id))


def place(world: World, test: str, patient: str) -> None:
    ordered = TESTS[test]
    indication = (
        ClinicalIndication.NON_SPECIFIC_COMPLAINT
        if ordered.takes_indication()
        else None
    )
    record = world["patients"][patient]
    world["order"] = practice_services.place_order(
        general_practitioner=record.general_practitioner,
        patient=record,
        test=ordered,
        indication=indication,
        now=NOW,
    )
    world["lab_order"] = LabOrder.objects.get(
        sample__sample_id=record.sample_id, test=ordered
    )


@given(
    parsers.parse('"{patient}" has NHANES CBC values and ferritin {ferritin:g} ng/mL')
)
def nhanes_values(world: World, patient: str, ferritin: float) -> None:
    participant = tube(world["patients"][patient])
    participant.cbc = {var: float(index) for index, var in enumerate(CBC_VARS, 1)}
    participant.ferritin = ferritin
    participant.save()


@given(parsers.parse('patient "{patient}" of "{owner}" without NHANES ferritin'))
def patient_without_ferritin(world: World, patient: str, owner: str) -> None:
    from tests.conftest import make_patient
    from web.vocabulary import RegisteredSex

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
    services.receive(sample=world["lab_order"].sample, now=NOW)


@given(parsers.re(r'a received (?P<test>CBC|ferritin) sample for "(?P<patient>[^"]+)"'))
def a_received_sample(world: World, test: str, patient: str) -> None:
    a_received_order(world, test, patient)


@given(
    parsers.re(r'an analysed (?P<test>CBC|ferritin) sample for "(?P<patient>[^"]+)"')
)
def an_analysed_sample(world: World, test: str, patient: str) -> None:
    a_received_order(world, test, patient)
    services.run_analyser(lab_order=world["lab_order"], now=NOW)


@when("laboratory staff receive the order")
def receive(world: World) -> None:
    sample = Sample.objects.get(pk=world["lab_order"].sample_id)
    try:
        services.receive(sample=sample, now=NOW)
    except ValidationError as error:
        world["error"] = error


@when("laboratory staff run the analyser")
def run_analyser(world: World) -> None:
    lab_order = LabOrder.objects.get(pk=world["lab_order"].pk)
    try:
        world["lab_order"] = services.run_analyser(lab_order=lab_order, now=NOW)
    except ValidationError as error:
        world["error"] = error


@then(parsers.parse('the sample of "{patient}" is received at the current time'))
def sample_received(world: World, patient: str) -> None:
    sample = Sample.objects.get(sample_id=world["patients"][patient].sample_id)
    assert sample.received_at == NOW


@then(parsers.parse('{action} is refused with code "{code}"'))
def refused(world: World, action: str, code: str) -> None:
    assert world["error"].code == code


@then(parsers.parse('the sample has the 13 NHANES CBC values of "{patient}"'))
def sample_has_cbc(world: World, patient: str) -> None:
    lab_order = world["lab_order"]
    assert lab_order.results == tube(world["patients"][patient]).cbc
    assert len(lab_order.results) == 13
    assert lab_order.analysed_at == NOW


@then("running the analyser is not offered for the order")
def analyser_not_offered(world: World) -> None:
    lab_order = world["lab_order"]
    assert lab_order not in queries.lab_orders_to_analyse()
    assert lab_order.sample in queries.samples_to_receive()


@then("the ferritin order is ready to analyse without being received")
def ready_without_receiving(world: World) -> None:
    assert world["lab_order"].test == OrderedTest.FERRITIN
    assert world["lab_order"] in queries.lab_orders_to_analyse()


@then(parsers.parse("the sample has ferritin {ferritin:g} ng/mL"))
def sample_has_ferritin(world: World, ferritin: float) -> None:
    assert world["lab_order"].ferritin == ferritin


@then("the sample's ferritin is not available in the demo data")
def ferritin_not_available(world: World) -> None:
    assert world["lab_order"].analysed_at == NOW
    assert world["lab_order"].ferritin is None


@then(
    "the lab's samples hold sample ID, ordering general practitioner, registered sex,"
    " age, test, indication and results"
)
def lab_rows_hold(world: World) -> None:
    (lab_order,) = queries.lab_orders_to_analyse()
    assert lab_order.sample.sample_id == world["order"].sample_id
    assert lab_order.general_practitioner == "Dr. Demo A"
    assert lab_order.get_registered_sex_display() == "Female"
    assert lab_order.get_test_display() == "CBC"


@then("no lab query returns the patient's name")
def no_patient_name(world: World) -> None:
    # The lab's models have no relation to the general practitioner's records.
    for model in (Sample, LabOrder):
        related = {field.related_model for field in model._meta.get_fields()}
        assert not related & {Patient}, model
    for lab_order in queries.lab_orders_to_analyse():
        assert "Test Patient" not in str(vars(lab_order))
