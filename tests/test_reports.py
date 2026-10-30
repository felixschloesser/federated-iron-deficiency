"""Scenarios: lab reports for the general practitioner (features/reports.feature)."""

from datetime import UTC, datetime

import pytest
from pytest_bdd import given, parsers, scenarios, then

from iron_deficiency.dataset import CBC_VARS
from tests.conftest import World
from web.practice import services
from web.practice.models import Order, Patient
from web.vocabulary import ClinicalIndication
from web.vocabulary import Test as OrderedTest

NOW = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)
# A distinct value per CBC variable, so a value under the wrong name shows.
CBC = {var: float(index) for index, var in enumerate(CBC_VARS, 1)}
pytestmark = pytest.mark.django_db

scenarios("reports.feature")


def order(patient: Patient, test: OrderedTest) -> Order:
    return services.place_order(
        general_practitioner=patient.general_practitioner,
        patient=patient,
        test=test,
        indication=ClinicalIndication.NON_SPECIFIC_COMPLAINT
        if test.takes_indication()
        else None,
        now=NOW,
    )


def lab_report(
    world: World,
    patient: str,
    test: OrderedTest,
    results: dict[str, float],
    *,
    ferritin_suggested: bool,
) -> None:
    from web.practice.models import LabReport

    world["lab_report"] = LabReport.objects.create(
        order=order(world["patients"][patient], test),
        results=results,
        ferritin_suggested=ferritin_suggested,
        released_at=NOW,
        fetched_at=NOW,
    )
    world["results"] = results


@given(
    parsers.re(
        r'a CBC lab report for "(?P<patient>[^"]+)"'
        r" (?P<suggested>with|without) ferritin suggested"
    )
)
def cbc_lab_report(world: World, patient: str, suggested: str) -> None:
    lab_report(
        world, patient, OrderedTest.CBC, CBC, ferritin_suggested=suggested == "with"
    )


@given(
    parsers.parse(
        'a ferritin lab report for "{patient}" with ferritin {ferritin:g} ng/mL'
    )
)
def ferritin_lab_report(world: World, patient: str, ferritin: float) -> None:
    lab_report(
        world,
        patient,
        OrderedTest.FERRITIN,
        {"LBXFER": ferritin},
        ferritin_suggested=False,
    )


@given(parsers.parse('a ferritin lab report for "{patient}" without a value'))
def ferritin_without_value(world: World, patient: str) -> None:
    lab_report(world, patient, OrderedTest.FERRITIN, {}, ferritin_suggested=False)


@given(parsers.parse('a ferritin order for "{patient}"'))
def ferritin_order(world: World, patient: str) -> None:
    order(world["patients"][patient], OrderedTest.FERRITIN)


@then(
    parsers.parse(
        'the lab report shows "{name}" in "{unit}" with the analyser\'s value'
    )
)
def shows_value(world: World, name: str, unit: str) -> None:
    (value,) = [value for value in world["lab_report"].values() if value.name == name]
    assert value.unit == unit
    assert value.value == world["results"][value.variable]


@then("the lab report shows 13 values in the order of the CBC")
def thirteen_values(world: World) -> None:
    assert [value.variable for value in world["lab_report"].values()] == CBC_VARS


@then("the lab report shows no values")
def no_values(world: World) -> None:
    assert world["lab_report"].values() == []


@then(parsers.parse('the lab report\'s comment is "{comment}"'))
def comment(world: World, comment: str) -> None:
    assert world["lab_report"].comment == comment


@then("the lab report has no comment")
def no_comment(world: World) -> None:
    assert world["lab_report"].comment == ""


def offered(world: World) -> bool:
    from web.practice.queries import ferritin_order_offered

    return ferritin_order_offered(world["lab_report"])


@then("ordering ferritin is offered on the lab report")
def ferritin_offered(world: World) -> None:
    assert offered(world)


@then("ordering ferritin is not offered on the lab report")
def ferritin_not_offered(world: World) -> None:
    assert not offered(world)


def test_every_cbc_value_and_ferritin_has_a_name_in_cbc_order() -> None:
    from web.vocabulary import RESULT_NAMES

    assert list(RESULT_NAMES) == [*CBC_VARS, "LBXFER"]
