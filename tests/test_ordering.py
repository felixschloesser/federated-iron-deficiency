"""Scenarios: ordering a test (features/ordering.feature), and ordering for
another general practitioner's patient (features/access.feature)."""

from datetime import UTC, datetime

from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.db import IntegrityError, transaction
from pytest_bdd import given, parsers, scenario, scenarios, then, when

from tests.conftest import World
from web.practice import services
from web.practice.models import Order
from web.vocabulary import ClinicalIndication, RegisteredSex
from web.vocabulary import Test as OrderedTest

NOW = datetime(2026, 10, 29, 9, 0, tzinfo=UTC)
TESTS = {"a CBC": OrderedTest.CBC, "ferritin": OrderedTest.FERRITIN}

scenarios("ordering.feature")


@scenario(
    "access.feature",
    "A general practitioner cannot collect a sample from another general"
    " practitioner's patient",
)
def test_a_general_practitioner_cannot_collect_from_another_general_practitioners_patient() -> (
    None
):
    pass


def indication_named(text: str) -> ClinicalIndication:
    return {choice.label.lower(): choice for choice in ClinicalIndication}[text]


@given(parsers.parse('"{general_practitioner}" collected a sample from "{patient}"'))
@when(parsers.parse('"{general_practitioner}" collects a sample from "{patient}"'))
def collect(world: World, general_practitioner: str, patient: str) -> None:
    try:
        world["sample"] = services.collect_sample(
            general_practitioner=world["general_practitioners"][general_practitioner],
            patient=world["patients"][patient],
            now=NOW,
        )
    except ValidationError as error:
        world["error"] = error


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
    """An order on the patient's latest sample."""
    try:
        world["order"] = services.place_order(
            general_practitioner=world["general_practitioners"][general_practitioner],
            sample=world["patients"][patient].samples.latest("pk"),
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


@then(parsers.parse('the order is refused with code "{code}"'))
def order_refused(world: World, code: str) -> None:
    """A condition across the order's fields: not one field's error (CLAUDE.md)."""
    assert "order" not in world
    errors = world["error"].error_dict
    assert [error.code for error in errors[NON_FIELD_ERRORS]] == [code]
    assert set(errors) == {NON_FIELD_ERRORS}


@when("a CBC order without an indication is written straight to the database")
def write_straight(world: World) -> None:
    sample = world["sample"]
    try:
        with transaction.atomic():
            Order.objects.create(
                sample=sample,
                test=OrderedTest.CBC,
                indication=None,
                registered_sex=sample.patient.registered_sex,
                age=sample.patient.age,
                ordered_at=NOW,
            )
    except IntegrityError as error:
        world["integrity_error"] = error


@then("the database refuses it")
def database_refuses(world: World) -> None:
    assert "integrity_error" in world


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
        sample=world["patients"][patient].samples.latest("pk"),
        test=OrderedTest.CBC,
        indication=indication_named(indication),
        now=NOW,
    )


@then(parsers.parse('the collection is refused with code "{code}" on field "{field}"'))
def collection_refused(world: World, code: str, field: str) -> None:
    assert [error.code for error in world["error"].error_dict[field]] == [code]


@then(
    parsers.re(
        r'the (?P<what>sample|order) is (?:on )?sample (?P<number>\d+) of "(?P<patient>[^"]+)"'
        r"(?P<now>, collected at the current time)?$"
    )
)
def numbered_sample(
    world: World, what: str, number: str, patient: str, now: str | None
) -> None:
    sample = world["sample"] if what == "sample" else world["order"].sample
    record = world["patients"][patient]
    assert sample.patient == record
    assert sample.sample_id == f"{record.nhanes_number}-{number}"
    if now:
        assert sample.collected_at == NOW
