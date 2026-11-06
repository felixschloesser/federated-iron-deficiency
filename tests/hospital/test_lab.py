"""Scenarios: analysing samples, and the lab never seeing a patient's name
(features/hospital/lab.feature). Only the hospital's side: lab orders arrive as its
messaging endpoint records them."""

from datetime import UTC, datetime, timedelta

import pytest
from django.core.exceptions import ValidationError
from pytest_bdd import given, parsers, scenarios, then, when

from ml.cohort import CBC_VARS
from tests.conftest import World
from tests.hospital.conftest import make_practice, make_tube, receive_lab_order
from web.hospital.lab.models import LabOrder, Sample
from web.hospital.nhanes.models import FERRITIN, Participant
from web.vocabulary import RegisteredSex
from web.vocabulary import Test as OrderedTest

NOW = datetime(2026, 10, 29, 10, 0, tzinfo=UTC)
TESTS = {"CBC": OrderedTest.CBC, "ferritin": OrderedTest.FERRITIN}
pytestmark = pytest.mark.django_db

scenarios("hospital/lab.feature")


def tube(world: World, patient: str) -> Participant:
    """What the patient's samples measure, at the hospital's analyser stand-in."""
    return Participant.objects.get(seqn=world["patients"][patient]["seqn"])


def place(world: World, test: str, patient: str) -> None:
    """A new sample of the patient arriving with its lab order."""
    record = world["patients"][patient]
    record["samples"] += 1
    world["lab_order"] = receive_lab_order(
        f"{record['seqn']}-{record['samples']}",
        TESTS[test],
        NOW,
        sex=record["sex"],
        age=record["age"],
    )


@given(
    parsers.parse(
        'practice "{practice}" sends samples of patient "{patient}",'
        " registered sex {sex}, aged {age:d}"
    )
)
def practice_sends_samples(
    world: World, practice: str, patient: str, sex: str, age: int
) -> None:
    make_practice()
    world["patients"][patient] = {
        "seqn": make_tube().seqn,
        "sex": RegisteredSex(sex),
        "age": age,
        "samples": 0,
    }


@given(
    parsers.parse('"{patient}" has NHANES CBC values and ferritin {ferritin:g} ng/mL')
)
def nhanes_values(world: World, patient: str, ferritin: float) -> None:
    participant = tube(world, patient)
    participant.cbc = {var: float(index) for index, var in enumerate(CBC_VARS, 1)}
    participant.ferritin = ferritin
    participant.save()


@given(parsers.parse('patient "{patient}" without NHANES ferritin'))
def patient_without_ferritin(world: World, patient: str) -> None:
    world["patients"][patient] = {
        "seqn": make_tube().seqn,
        "sex": RegisteredSex.FEMALE,
        "age": 30,
        "samples": 0,
    }


@given(parsers.re(r'a (?P<test>CBC|ferritin) order for "(?P<patient>[^"]+)"$'))
def an_order(world: World, test: str, patient: str) -> None:
    place(world, test, patient)


@given("a ferritin order on that sample")
def ferritin_on_that_sample(world: World) -> None:
    analysed = world["lab_order"]
    world["lab_order"] = receive_lab_order(
        analysed.sample.sample_id,
        OrderedTest.FERRITIN,
        NOW,
        sex=RegisteredSex(analysed.registered_sex),
        age=analysed.age,
    )


@given(
    parsers.re(r'an analysed (?P<test>CBC|ferritin) sample for "(?P<patient>[^"]+)"')
)
def an_analysed_sample(world: World, test: str, patient: str) -> None:
    place(world, test, patient)
    world["lab_order"].run_analyser(directory=None, now=NOW)


@given(
    parsers.parse('the analyser stand-in has no values for the sample of "{patient}"')
)
def no_tube(world: World, patient: str) -> None:
    tube(world, patient).delete()


@when("laboratory staff run the analyser")
def run_analyser(world: World) -> None:
    lab_order = LabOrder.objects.get(pk=world["lab_order"].pk)
    try:
        world["lab_order"] = lab_order.run_analyser(directory=None, now=NOW)
    except ValidationError as error:
        world["error"] = error


PAGES = {"first": 0, "second": 1}


@given("laboratory staff opened the CBC order on two pages")
def two_pages(world: World) -> None:
    """Two copies of the lab order as loaded, like two open tabs or two staff."""
    world["pages"] = [LabOrder.objects.get(pk=world["lab_order"].pk) for _ in PAGES]


@when(parsers.parse("laboratory staff run the analyser from the {page} page"))
def run_analyser_from(world: World, page: str) -> None:
    number = PAGES[page]
    try:
        world["pages"][number].run_analyser(
            directory=None,
            now=NOW + timedelta(minutes=number),
        )
    except ValidationError as error:
        world["error"] = error


@then("the CBC order keeps the analysis from the first page")
def keeps_first_analysis(world: World) -> None:
    assert LabOrder.objects.get(pk=world["lab_order"].pk).analysed_at == NOW


@then(parsers.parse('{action} is refused with code "{code}"'))
def refused(world: World, action: str, code: str) -> None:
    assert world["error"].code == code


@then(parsers.parse('the sample has the 13 NHANES CBC values of "{patient}"'))
def sample_has_cbc(world: World, patient: str) -> None:
    lab_order = world["lab_order"]
    assert lab_order.results == tube(world, patient).cbc
    assert len(lab_order.results) == 13
    assert lab_order.analysed_at == NOW


@then(parsers.re(r"the (?P<test>CBC|ferritin) order is ready to analyse"))
def ready_to_analyse(world: World, test: str) -> None:
    assert world["lab_order"].test == TESTS[test]
    assert world["lab_order"] in LabOrder.objects.to_analyse()


@then(parsers.re(r"its sample is (?P<negated>not )?a stored sample"))
def stored_sample(world: World, negated: str | None) -> None:
    (row,) = [
        row for row in LabOrder.objects.to_analyse() if row.pk == world["lab_order"].pk
    ]
    assert row.stored_sample is (negated is None)


@then(parsers.parse("the sample has ferritin {ferritin:g} ng/mL"))
def sample_has_ferritin(world: World, ferritin: float) -> None:
    assert world["lab_order"].results == {FERRITIN: ferritin}


@then("the sample's ferritin is not available in the demo data")
def ferritin_not_available(world: World) -> None:
    assert world["lab_order"].analysed_at == NOW
    assert world["lab_order"].results == {}


@then(
    "the lab's samples hold sample ID, registered sex, age, test, whether the"
    " indication is screened and results, and no general practitioner"
)
def lab_rows_hold(world: World) -> None:
    (lab_order,) = LabOrder.objects.to_analyse()
    assert lab_order.sample.sample_id == world["lab_order"].sample.sample_id
    # The practice, by its name, stands for its one general practitioner.
    fields = {field.name for field in LabOrder._meta.fields}
    assert not {"general_practitioner", "name", "patient"} & fields
    assert lab_order.get_registered_sex_display() == "Female"
    assert lab_order.get_test_display() == "CBC"
    # Ordered for a screened indication, which is all the lab learns of it.
    assert lab_order.screened_indication is True


@then("the lab's records relate to nothing outside the hospital")
def lab_relates_to_the_hospital_only(world: World) -> None:
    # So no lab query can reach a general practitioner's records, and with them
    # a patient's name.
    for model in (Sample, LabOrder):
        related = {
            field.related_model._meta.app_label
            for field in model._meta.get_fields()
            if field.related_model is not None
        }
        assert related <= {"lab", "deployment", "nhanes"}, (model, related)
