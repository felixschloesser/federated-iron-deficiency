"""Scenarios: ordering a test (features/ordering.feature), and the practice's one
general practitioner (features/access.feature)."""

from datetime import UTC, datetime

from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.db import IntegrityError, transaction
from pytest_bdd import given, parsers, scenario, scenarios, then, when

from tests.conftest import World
from web.practice.models import Order
from web.vocabulary import ClinicalIndication, RegisteredSex
from web.vocabulary import Test as OrderedTest

NOW = datetime(2026, 10, 29, 9, 0, tzinfo=UTC)
TESTS = {"a CBC": OrderedTest.CBC, "ferritin": OrderedTest.FERRITIN}

scenarios("ordering.feature")


@scenario("access.feature", "A practice has one general practitioner")
def test_a_practice_has_one_general_practitioner() -> None:
    pass


@when(parsers.parse('general practitioner "{name}" is added to the practice'))
def add_general_practitioner(world: World, name: str) -> None:
    from web.accounts.models import User
    from web.practice.models import GeneralPractitioner

    added = GeneralPractitioner(user=User.objects.create_user(username="b"), name=name)
    try:
        added.full_clean()
    except ValidationError as error:
        world["error"] = error
    try:
        with transaction.atomic():
            added.save()
    except IntegrityError as error:
        world["integrity_error"] = error


@then(parsers.parse('adding them is refused with code "{code}"'))
def adding_refused(world: World, code: str) -> None:
    assert [error.code for error in world["error"].error_dict[NON_FIELD_ERRORS]] == [
        code
    ]


def indication_named(text: str) -> ClinicalIndication:
    return {choice.label.lower(): choice for choice in ClinicalIndication}[text]


@given(parsers.parse('"{general_practitioner}" collected a sample from "{patient}"'))
@when(parsers.parse('"{general_practitioner}" collects a sample from "{patient}"'))
def collect(world: World, general_practitioner: str, patient: str) -> None:
    try:
        world["sample"] = world["general_practitioners"][
            general_practitioner
        ].collect_sample(
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
        world["order"] = world["general_practitioners"][
            general_practitioner
        ].place_order(
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


@then(parsers.parse('the order is refused with code "{code}" on field "{field}"'))
def order_refused_on(world: World, code: str, field: str) -> None:
    assert "order" not in world
    errors = world["error"].error_dict
    found = {name: [error.code for error in each] for name, each in errors.items()}
    assert found == {field: [code]}


@given(
    parsers.re(
        r"the sample has a CBC lab report"
        r" (?P<suggestion>suggesting ferritin|without a suggestion)$"
    )
)
def sample_has_lab_report(world: World, suggestion: str) -> None:
    from web.practice.models import LabReport

    sample = world["sample"]
    cbc = sample.patient.general_practitioner.place_order(
        sample=sample,
        test=OrderedTest.CBC,
        indication=ClinicalIndication.OTHER,
        now=NOW,
    )
    LabReport.objects.create(
        order=cbc,
        results={},
        ferritin_suggested=suggestion == "suggesting ferritin",
        released_at=NOW,
        fetched_at=NOW,
    )


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
    world["general_practitioners"][general_practitioner].place_order(
        sample=world["patients"][patient].samples.latest("pk"),
        test=OrderedTest.CBC,
        indication=indication_named(indication),
        now=NOW,
    )


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


@given(parsers.parse('the practice works with laboratories "{first}" and "{second}"'))
def laboratories(first: str, second: str) -> None:
    from web.practice.models import Laboratory

    for name in (first, second):
        Laboratory.objects.create(name=name, address="127.0.0.1:1")


@when(
    parsers.parse(
        '"{general_practitioner}" collects a sample from "{patient}" for "{laboratory}"'
    )
)
def collect_for(
    world: World, general_practitioner: str, patient: str, laboratory: str
) -> None:
    from web.practice.models import Laboratory

    world["sample"] = world["general_practitioners"][
        general_practitioner
    ].collect_sample(
        patient=world["patients"][patient],
        laboratory=Laboratory.objects.get(name=laboratory),
        now=NOW,
    )


@then(parsers.parse('the sample goes to "{laboratory}"'))
def sample_goes_to(world: World, laboratory: str) -> None:
    assert world["sample"].laboratory.name == laboratory


@then(parsers.parse('the collection is refused with code "{code}" on field "{field}"'))
def collection_refused(world: World, code: str, field: str) -> None:
    assert [error.code for error in world["error"].error_dict[field]] == [code]
