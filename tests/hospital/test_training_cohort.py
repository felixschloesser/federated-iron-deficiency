"""Scenarios: providing the training cohort (features/hospital/training_cohort.feature)."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse
from pytest_bdd import given, parsers, scenarios, then, when
from pytest_django.fixtures import Settings

from ml.cohort import FEATURES
from tests.conftest import World
from tests.hospital.conftest import (
    found_cohort,
    make_lab_records,
    make_laboratory_director,
    make_laboratory_staff_member,
)
from web.shared.vocabulary import RegisteredSex

NOW = datetime(2026, 11, 6, 9, 0, tzinfo=UTC)
pytestmark = pytest.mark.django_db

scenarios("hospital/training_cohort.feature")


@pytest.fixture
def cohort_dir(tmp_path: Path) -> Path:
    return tmp_path / "cohort"


@given(parsers.parse('laboratory director "{name}"'))
def laboratory_director(world: World, db: None, name: str) -> None:
    world["director"] = make_laboratory_director(name)


@given(
    parsers.parse(
        "lab records of {count:d} eligible past patients, {deficient:d} of them iron"
        " deficient"
    )
)
def eligible_records(count: int, deficient: int) -> None:
    make_lab_records(count, iron_deficient=deficient)


@given(parsers.parse("lab records of {count:d} patients who are not eligible"))
def ineligible_records(count: int) -> None:
    # Men, and women outside the eligible ages, each with a ferritin result.
    make_lab_records(count // 3, iron_deficient=1, sex=RegisteredSex.MALE)
    make_lab_records(count // 3, iron_deficient=1, age=17)
    make_lab_records(count - 2 * (count // 3), iron_deficient=1, age=50)


@given(
    parsers.parse(
        "lab records of {count:d} eligible past patients without a ferritin result"
    )
)
def records_without_ferritin(count: int) -> None:
    make_lab_records(count, with_ferritin=False)


@given(
    parsers.parse(
        "lab records of {count:d} eligible past patients whose CBC was ordered at"
        " the start of pregnancy"
    )
)
def records_at_start_of_pregnancy(count: int) -> None:
    from web.shared.vocabulary import ClinicalIndication

    make_lab_records(count, indication=ClinicalIndication.START_OF_PREGNANCY)


@given(
    parsers.parse(
        "lab records of {count:d} more eligible past patients, none of them iron"
        " deficient"
    )
)
def more_records(count: int) -> None:
    make_lab_records(count)


@given(
    parsers.parse(
        "the lab records hold only {count:d} eligible past patients, {deficient:d}"
        " of them iron deficient"
    )
)
def only_records(count: int, deficient: int) -> None:
    from web.hospital.cohort.models import LabRecord

    LabRecord.objects.all().delete()
    make_lab_records(count, iron_deficient=deficient)


def provide(world: World, cohort_dir: Path) -> None:
    from web.hospital.cohort.models import TrainingCohort

    try:
        TrainingCohort.objects.provide(
            directory=cohort_dir, by=world["director"], now=NOW
        )
    except ValidationError as error:
        world["error"] = error


@given("the laboratory director provided the training cohort")
def provided(world: World, cohort_dir: Path) -> None:
    from web.hospital.cohort.models import TrainingCohort

    world["earlier"] = TrainingCohort.objects.provide(
        directory=cohort_dir, by=world["director"], now=NOW
    )


@when("the laboratory director provides the training cohort")
def provides(world: World, cohort_dir: Path) -> None:
    provide(world, cohort_dir)


@when("the laboratory director withdraws the training cohort")
def withdraws(world: World, cohort_dir: Path) -> None:
    from web.hospital.cohort.models import TrainingCohort

    try:
        TrainingCohort.objects.withdraw(
            directory=cohort_dir, by=world["director"], now=NOW
        )
    except ValidationError as error:
        world["error"] = error


@given(parsers.parse('laboratory staff member "{name}"'))
def staff_member(world: World, name: str) -> None:
    world["staff_member"] = make_laboratory_staff_member(name)


@when(parsers.parse('"{name}" tries to provide the training cohort'))
def staff_tries(
    world: World, client: Client, settings: Settings, cohort_dir: Path, name: str
) -> None:
    settings.TRAINING_COHORT_DIR = cohort_dir
    client.force_login(world["staff_member"])
    client.post(reverse("cohort:provide"))


@then("no training cohort is provided")
def none_provided(cohort_dir: Path) -> None:
    from web.hospital.cohort.models import TrainingCohort

    assert TrainingCohort.objects.provided() is None
    assert found_cohort(cohort_dir) is None


@then(
    parsers.parse(
        "providing would hold {count:d} past patients, {deficient:d} of them iron"
        " deficient"
    )
)
def summary(count: int, deficient: int) -> None:
    from web.hospital.cohort.models import LabRecord

    held = LabRecord.objects.summary()
    assert (held.past_patients, held.iron_deficient) == (count, deficient)


@then(
    parsers.parse(
        "the startup's code at this hospital finds {count:d} rows of the 13 CBC"
        " values, age and the label, and nothing else"
    )
)
def finds_rows(cohort_dir: Path, count: int) -> None:
    rows = found_cohort(cohort_dir)
    assert rows is not None
    assert list(rows.columns) == [*FEATURES, "iron_deficient"]
    assert len(rows) == count


@then("the startup's code at this hospital finds no training cohort")
def finds_none(cohort_dir: Path) -> None:
    assert found_cohort(cohort_dir) is None


@then(parsers.parse('the training cohort is provided by "{name}", with its SHA-256'))
def provided_by(cohort_dir: Path, name: str) -> None:
    from web.hospital.cohort.models import TrainingCohort

    cohort = TrainingCohort.objects.provided()
    assert cohort is not None
    assert cohort.provided_by.username == name.lower().replace(" ", "-")
    assert cohort.provided_at == NOW
    # The folder the startup's code reads is named after the hash it holds.
    assert [path.name for path in cohort_dir.iterdir()] == [cohort.sha256]
    assert len(cohort.sha256) == 64


def assert_withdrawn_by(cohort_id: int, name: str) -> None:
    from web.hospital.cohort.models import TrainingCohort

    cohort = TrainingCohort.objects.get(pk=cohort_id)
    assert cohort.withdrawn_by is not None
    assert cohort.withdrawn_by.username == name.lower().replace(" ", "-")
    assert cohort.withdrawn_at == NOW


@then(parsers.parse('the training cohort is recorded as withdrawn by "{name}"'))
def withdrawn(world: World, name: str) -> None:
    from web.hospital.cohort.models import TrainingCohort

    assert TrainingCohort.objects.provided() is None
    assert_withdrawn_by(world["earlier"].pk, name)


@then(parsers.parse('the earlier training cohort is recorded as withdrawn by "{name}"'))
def earlier_withdrawn(world: World, name: str) -> None:
    from web.hospital.cohort.models import TrainingCohort

    assert_withdrawn_by(world["earlier"].pk, name)
    current = TrainingCohort.objects.provided()
    assert current is not None and current.pk != world["earlier"].pk


@then(parsers.parse('withdrawing is refused with code "{code}"'))
@then(parsers.parse('providing is refused with code "{code}"'))
def refused(world: World, code: str) -> None:
    assert [error.code for error in world["error"].error_list] == [code]
