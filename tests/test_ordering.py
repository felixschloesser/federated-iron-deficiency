"""Scenarios: ordering a test (features/ordering.feature), and ordering for
another general practitioner's patient (features/access.feature)."""

from datetime import UTC, datetime

from django.core.exceptions import ValidationError
from pytest_bdd import given, parsers, scenario, scenarios, then, when

from tests.conftest import World
from web.practice import services
from web.vocabulary import ClinicalIndication, RegisteredSex
from web.vocabulary import Test as OrderedTest

NOW = datetime(2026, 10, 29, 9, 0, tzinfo=UTC)
TESTS = {"a CBC": OrderedTest.CBC, "ferritin": OrderedTest.FERRITIN}

scenarios("ordering.feature")


@scenario(
    "access.feature",
    "A general practitioner cannot order for another general practitioner's patient",
)
def test_a_general_practitioner_cannot_order_for_another_general_practitioners_patient() -> (
    None
):
    pass


def indication_named(text: str) -> ClinicalIndication:
    return {choice.label.lower(): choice for choice in ClinicalIndication}[text]


@when(
    parsers.re(
        r'"(?P<general_practitioner>[^"]+)" orders (?P<test>a CBC|ferritin) for "(?P<patient>[^"]+)"'
        r"(?: with indication (?P<indication>.+)| without an indication)?$"
    )
)
def place_order(
    world: World,
    general_practitioner: str,
    test: str,
    patient: str,
    indication: str | None,
) -> None:
    try:
        world["order"] = services.place_order(
            general_practitioner=world["general_practitioners"][general_practitioner],
            patient=world["patients"][patient],
            test=TESTS[test],
            indication=indication_named(indication) if indication else None,
            now=NOW,
        )
    except ValidationError as error:
        world["error"] = error


@then(
    parsers.re(
        r"the order has test (?P<test>CBC|ferritin)"
        r" and (?:indication (?P<indication>.+)|no indication)$"
    )
)
def order_has_test(world: World, test: str, indication: str | None) -> None:
    order = world["order"]
    assert order.test == OrderedTest(test.lower())
    expected = indication_named(indication) if indication else None
    assert order.indication == expected


@then(parsers.parse("the order has registered sex {sex} and age {age:d}"))
def order_copies_patient(world: World, sex: str, age: int) -> None:
    assert world["order"].registered_sex == RegisteredSex(sex)
    assert world["order"].age == age


@then(parsers.parse('the order is refused with code "{code}" on field "{field}"'))
def order_refused(world: World, code: str, field: str) -> None:
    assert "order" not in world
    assert [error.code for error in world["error"].error_dict[field]] == [code]


@given(
    parsers.re(
        r'"(?P<general_practitioner>[^"]+)" ordered a CBC for "(?P<patient>[^"]+)"'
        r" with indication (?P<indication>.+)$"
    )
)
def ordered_before(
    world: World, general_practitioner: str, patient: str, indication: str
) -> None:
    services.place_order(
        general_practitioner=world["general_practitioners"][general_practitioner],
        patient=world["patients"][patient],
        test=OrderedTest.CBC,
        indication=indication_named(indication),
        now=NOW,
    )


@then(parsers.parse('the order carries the sample ID of "{patient}"'))
def order_carries_sample_id(world: World, patient: str) -> None:
    assert world["order"].sample_id == world["patients"][patient].sample_id


@then(parsers.parse('both orders carry the sample ID of "{patient}"'))
def both_carry_sample_id(world: World, patient: str) -> None:
    record = world["patients"][patient]
    assert [order.sample_id for order in record.orders.all()] == [record.sample_id] * 2
