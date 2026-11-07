"""Scenarios: a training run trains on one training cohort per hospital
(features/training_cohort_in_runs.feature), through the reader the ClientApp's
load_cohort calls; a run's state is the SHA-256 it noted, as load_cohort keeps
it in Flower's context.state from round to round. Flower itself is not
imported here: it warns on import (click 8.3), and the containers run it."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from ml.cohort import FEATURES
from tests.conftest import World
from tests.hospital.conftest import make_lab_records, make_laboratory_director

NOW = datetime(2026, 11, 6, 9, 0, tzinfo=UTC)
pytestmark = pytest.mark.django_db

scenarios("training_cohort_in_runs.feature")


@pytest.fixture
def cohort_dir(tmp_path: Path) -> Path:
    return tmp_path / "cohort"


@given("a hospital whose laboratory director provided the training cohort")
def provided(world: World, db: None, cohort_dir: Path) -> None:
    from hospital.cohort.models import TrainingCohort

    world["director"] = make_laboratory_director("Director One")
    make_lab_records(120, iron_deficient=20)
    TrainingCohort.objects.provide(directory=cohort_dir, by=world["director"], now=NOW)


def read(world: World, cohort_dir: Path) -> None:
    from ml.training_cohort import TrainingCohortUnavailable, read_training_cohort

    try:
        world["noted"], world["rows"] = read_training_cohort(
            cohort_dir, world.get("noted")
        )
    except TrainingCohortUnavailable as error:
        world["error"] = error


@when(
    "the startup's code at the hospital reads the training cohort in a run's first"
    " round"
)
@given(
    "the startup's code at the hospital read the training cohort in a run's first round"
)
def first_round(world: World, cohort_dir: Path) -> None:
    world.pop("noted", None)
    read(world, cohort_dir)


@when(
    "the startup's code at the hospital reads the training cohort in another run's"
    " first round"
)
def another_run(world: World, cohort_dir: Path) -> None:
    # A new run starts with nothing noted.
    world.pop("noted", None)
    read(world, cohort_dir)


@when("it reads the training cohort in the run's next round")
def next_round(world: World, cohort_dir: Path) -> None:
    world.pop("rows", None)
    read(world, cohort_dir)


@given("the laboratory director withdrew the training cohort")
def withdrew(world: World, cohort_dir: Path) -> None:
    from hospital.cohort.models import TrainingCohort

    TrainingCohort.objects.withdraw(directory=cohort_dir, by=world["director"], now=NOW)


@given(
    "the laboratory director provided a new training cohort after new lab records"
    " arrived"
)
def provided_new(world: World, cohort_dir: Path) -> None:
    from hospital.cohort.models import TrainingCohort

    make_lab_records(5)
    TrainingCohort.objects.provide(directory=cohort_dir, by=world["director"], now=NOW)


@then("it reads the provided training cohort's rows")
def reads_provided(world: World) -> None:
    from hospital.cohort.models import TrainingCohort

    provided = TrainingCohort.objects.provided()
    assert provided is not None
    assert "error" not in world, world.get("error")
    rows = world["rows"]
    assert list(rows.columns) == [*FEATURES, "iron_deficient"]
    assert len(rows) == provided.past_patients
    assert int(rows["iron_deficient"].sum()) == provided.iron_deficient
    assert world["noted"] == provided.sha256


@then(parsers.parse('reading fails, naming "{reason}"'))
def fails(world: World, reason: str) -> None:
    assert "rows" not in world
    assert reason in str(world["error"])
