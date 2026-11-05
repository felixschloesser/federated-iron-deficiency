"""Scenarios: deploying a screening model (features/deployment.feature)."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse
from pytest_bdd import given, parsers, scenarios, then, when
from pytest_django.fixtures import Settings

from iron_deficiency.screening import Problem
from tests.conftest import World, make_laboratory_staff_member, write_final_model

NOW = datetime(2026, 10, 30, 9, 0, tzinfo=UTC)
pytestmark = pytest.mark.django_db

scenarios("deployment.feature")


@pytest.fixture
def final_models_dir(tmp_path: Path) -> Path:
    return tmp_path / "final-models"


@given(parsers.parse('laboratory director "{name}"'))
def laboratory_director(
    world: World, db: None, name: str, final_models_dir: Path
) -> None:
    from tests.conftest import make_laboratory_director

    world["director"] = make_laboratory_director(name)
    world["final_models_dir"] = final_models_dir
    final_models_dir.mkdir(parents=True)


@when(parsers.parse('laboratory director "{name}" is added to the hospital'))
def add_laboratory_director(world: World, name: str) -> None:
    from django.db import IntegrityError, transaction

    from web.accounts.models import User
    from web.deployment.models import LaboratoryDirector

    added = LaboratoryDirector(user=User.objects.create_user(username="two"), name=name)
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
    from django.core.exceptions import NON_FIELD_ERRORS

    errors = world["error"].error_dict
    assert [error.code for error in errors[NON_FIELD_ERRORS]] == [code]


@then("the database refuses the second director")
def database_refuses_director(world: World) -> None:
    assert "integrity_error" in world


@given(parsers.parse('screening model "{run_id}" with local validation:'))
def screening_model(world: World, run_id: str, datatable: list[list[str]]) -> None:
    rows = {row[0].strip(): row[1:] for row in datatable[1:]}
    world.setdefault("validation", {})[run_id] = {
        "true_positives": int(rows["deficient"][0]),
        "false_negatives": int(rows["deficient"][1]),
        "false_positives": int(rows["not deficient"][0]),
        "true_negatives": int(rows["not deficient"][1]),
    }
    world["last_run"] = run_id


@given(parsers.parse("its local AUROC is {auroc:g}"))
def local_auroc(world: World, auroc: float) -> None:
    run_id = world["last_run"]
    validation = {**world["validation"][run_id], "auroc": auroc}
    stored_at = NOW + timedelta(minutes=len(world.setdefault("stored", [])))
    world["stored"].append(run_id)
    write_final_model(world["final_models_dir"], run_id, validation, stored_at)


def deploy(world: World, run_id: str) -> None:
    from web.deployment.models import Deployment

    try:
        Deployment.objects.deploy(
            run_id=run_id, directory=world["final_models_dir"], now=NOW
        )
    except ValidationError as error:
        world["error"] = error


@given(parsers.parse('the laboratory director deployed "{first}", then "{second}"'))
def deployed_two(world: World, first: str, second: str) -> None:
    deploy(world, first)
    deploy(world, second)


@given(parsers.re(r'the laboratory director deployed "(?P<run_id>[^"]+)"$'))
def deployed_one(world: World, run_id: str) -> None:
    deploy(world, run_id)


@when(parsers.parse('the laboratory director deploys screening model "{run_id}"'))
def deploys(world: World, run_id: str) -> None:
    deploy(world, run_id)


PROBLEMS = {
    "is not a readable model file": None,
    "was trained on other features": {"n_features": 5},
    "has no threshold": {"leave_out": ("threshold",)},
    "has no standardization": {"leave_out": ("mean", "std")},
}


@given(parsers.parse('screening model "{run_id}" that {problem}'))
def broken_final_model(world: World, run_id: str, problem: str) -> None:
    path = world["final_models_dir"] / f"{run_id}.pt"
    variant = PROBLEMS[problem]
    if variant is None:
        path.write_bytes(b"not a model")
        return
    validation = {**world["validation"]["run-1"], "auroc": 0.8}
    write_final_model(
        path.parent, run_id, validation, NOW + timedelta(hours=1), **variant
    )


@given(parsers.parse('the file of the deployed "{run_id}" has changed on disk'))
def changed_on_disk(world: World, run_id: str) -> None:
    deploy(world, run_id)
    with (world["final_models_dir"] / f"{run_id}.pt").open("ab") as file:
        file.write(b"tampered")


@given(parsers.parse('laboratory staff member "{name}"'))
def staff_member(world: World, name: str) -> None:
    world["staff_member"] = make_laboratory_staff_member(name)


@when(parsers.parse('"{name}" tries to deploy screening model "{run_id}"'))
def staff_tries(
    world: World, client: Client, settings: Settings, name: str, run_id: str
) -> None:
    settings.FINAL_MODELS_DIR = world["final_models_dir"]
    client.force_login(world["staff_member"].user)
    client.post(reverse("deployment:deploy", kwargs={"run_id": run_id}))


def deployed_run(world: World) -> str | None:
    """The run ID of the model that screens now, if one can."""
    from web.deployment.models import Deployment, Screener

    deployed = Deployment.objects.screener(world["final_models_dir"])
    return deployed.screening_model.run_id if isinstance(deployed, Screener) else None


def no_usable_model(world: World) -> object:
    from web.deployment.models import Deployment, Screener

    deployed = Deployment.objects.screener(world["final_models_dir"])
    return None if isinstance(deployed, Screener) else deployed


@then("there is no deployed model")
def no_deployed_model(world: World) -> None:
    from web.deployment.models import NoUsableModel

    assert no_usable_model(world) is NoUsableModel.NO_DEPLOYED_MODEL


@then(parsers.parse('screening models "{first}" and "{second}" can be deployed'))
def can_be_deployed(world: World, first: str, second: str) -> None:
    from web.deployment.model_files import screening_models

    listed = {
        model.run_id: model for model in screening_models(world["final_models_dir"])
    }
    assert listed[first].problem is None
    assert listed[second].problem is None


@then(parsers.parse('"{run_id}" is the deployed model'))
def is_deployed(world: World, run_id: str) -> None:
    assert deployed_run(world) == run_id


@then(parsers.parse('the deployment history lists "{first}", "{second}", "{third}"'))
def history(world: World, first: str, second: str, third: str) -> None:
    from web.deployment.models import Deployment

    runs = [
        deployment.screening_model.run_id
        for deployment in Deployment.objects.order_by("deployed_at", "pk")
    ]
    assert runs == [first, second, third]


@then(
    parsers.re(
        r'(?:the screening models|they) show "(?P<run_id>[^"]+)", (?P<is_deployed>deployed, )?'
        r"with sensitivity (?P<sensitivity>\d+ of \d+), specificity (?P<specificity>\d+ of \d+),"
        r" positive predictive value (?P<ppv>\d+ of \d+),"
        r" negative predictive value (?P<npv>\d+ of \d+), AUROC (?P<auroc>[\d.]+)"
    )
)
def shows_validation(
    world: World,
    run_id: str,
    is_deployed: str | None,
    sensitivity: str,
    specificity: str,
    ppv: str,
    npv: str,
    auroc: str,
) -> None:
    from web.deployment.model_files import screening_models

    (model,) = [
        m for m in screening_models(world["final_models_dir"]) if m.run_id == run_id
    ]
    assert str(model.sensitivity) == sensitivity
    assert str(model.specificity) == specificity
    assert str(model.positive_predictive_value) == ppv
    assert str(model.negative_predictive_value) == npv
    assert model.local_auroc == pytest.approx(float(auroc))
    assert (deployed_run(world) == run_id) == bool(is_deployed)


@then(
    parsers.parse(
        'screening model "{run_id}" cannot be deployed, with reason code "{code}"'
    )
)
def cannot_be_deployed(world: World, run_id: str, code: str) -> None:
    from web.deployment.model_files import screening_models

    (model,) = [
        m for m in screening_models(world["final_models_dir"]) if m.run_id == run_id
    ]
    assert getattr(model.problem, "value", None) == code


@then(
    parsers.parse('deploying screening model "{run_id}" is refused with code "{code}"')
)
def deploying_refused(world: World, run_id: str, code: str) -> None:
    world.pop("error", None)
    deploy(world, run_id)
    assert world["error"].code == code


@then(parsers.parse('there is no usable deployed model, with reason code "{code}"'))
def no_usable(world: World, code: str) -> None:
    assert getattr(no_usable_model(world), "value", None) == code


@then("the Models page says the deployed model changed on disk")
def page_says_changed(world: World) -> None:
    assert "changed on disk" in str(getattr(no_usable_model(world), "label", ""))


@pytest.mark.parametrize("problem", Problem)
def test_every_problem_of_a_file_is_a_reason_it_cannot_be_deployed(
    problem: Problem,
) -> None:
    from web.deployment.model_files import CannotDeploy

    # The reason code is what the scenarios and the refusal's error code name.
    assert CannotDeploy.because(problem).value == problem.value
