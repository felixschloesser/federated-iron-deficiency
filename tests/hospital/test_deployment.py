"""Scenarios: deploying a screening model (features/hospital/deployment.feature)."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse
from pytest_bdd import given, parsers, scenarios, then, when
from pytest_django.fixtures import Settings

from ml.cohort import FEATURES
from tests.conftest import World
from tests.hospital.conftest import make_laboratory_staff_member, write_screening_model

NOW = datetime(2026, 10, 30, 9, 0, tzinfo=UTC)
pytestmark = pytest.mark.django_db

scenarios("hospital/deployment.feature")


@pytest.fixture
def screening_models_dir(tmp_path: Path) -> Path:
    return tmp_path / "screening-models"


@given(parsers.parse('laboratory director "{name}"'))
def laboratory_director(
    world: World, db: None, name: str, screening_models_dir: Path
) -> None:
    from tests.hospital.conftest import make_laboratory_director

    world["director"] = make_laboratory_director(name)
    world["screening_models_dir"] = screening_models_dir
    screening_models_dir.mkdir(parents=True)


@when(parsers.parse('laboratory director "{name}" is added to the hospital'))
def add_laboratory_director(world: World, name: str) -> None:
    from django.db import IntegrityError, transaction

    from web.shared.accounts.models import User
    from web.shared.accounts.roles import Role

    added = User(username="two", role=Role.LABORATORY_DIRECTOR)
    added.set_unusable_password()
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


def local_validation(datatable: list[list[str]]) -> dict[float, dict[str, int]]:
    """The confusion matrix at each threshold, one table row per threshold."""
    return {
        float(row[0]): {
            "true_positives": int(row[1]),
            "false_negatives": int(row[2]),
            "false_positives": int(row[3]),
            "true_negatives": int(row[4]),
        }
        for row in datatable[1:]
    }


def write(world: World, run_id: str) -> None:
    """(Re)write a screening model's file from what the scenario gave of it."""
    path = world["screening_models_dir"] / f"{run_id}.pt"
    path.unlink(missing_ok=True)
    write_screening_model(
        path.parent,
        run_id,
        world["validation"][run_id],
        world["stored_at"][run_id],
        local_auroc=world["auroc"][run_id],
    )


@given(parsers.parse('screening model "{run_id}" with local validation:'))
def screening_model(world: World, run_id: str, datatable: list[list[str]]) -> None:
    world.setdefault("validation", {})[run_id] = local_validation(datatable)
    world["last_run"] = run_id


@given(parsers.parse("its local AUROC is {auroc:g}"))
def local_auroc(world: World, auroc: float) -> None:
    run_id = world["last_run"]
    stored = world.setdefault("stored_at", {})
    stored[run_id] = NOW + timedelta(minutes=len(stored))
    world.setdefault("auroc", {})[run_id] = auroc
    write(world, run_id)


def deploy(world: World, run_id: str) -> None:
    from web.hospital.deployment.models import Deployment

    try:
        Deployment.objects.deploy(
            run_id=run_id,
            by=world["director"],
            directory=world["screening_models_dir"],
            now=next_moment(world),
        )
    except ValidationError as error:
        world["error"] = error


def next_moment(world: World) -> datetime:
    """A later time for each decision, so the history has an order."""
    world["moments"] = world.get("moments", 0) + 1
    return NOW + timedelta(minutes=world["moments"])


def set_target(world: World, percent: int) -> None:
    from web.hospital.deployment.models import TargetSensitivity

    try:
        TargetSensitivity.objects.set(
            percent=percent,
            by=world["director"],
            directory=world["screening_models_dir"],
            now=next_moment(world),
        )
    except ValidationError as error:
        world["error"] = error


@given(
    parsers.parse("the laboratory director set the target sensitivity to {percent:d}%")
)
@when(
    parsers.parse("the laboratory director sets the target sensitivity to {percent:d}%")
)
def sets_target(world: World, percent: int) -> None:
    set_target(world, percent)


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


# A file that is not whole, as each scenario row names it: the parts it leaves
# out, and the features its weights were trained on.
NOT_WHOLE: dict[str, tuple[tuple[str, ...], int]] = {
    "was trained on other features": ((), 5),
    "lacks its weights": (("state_dict",), len(FEATURES)),
    "misses an iron-deficient past patient at its lowest threshold": (
        (),
        len(FEATURES),
    ),
}


@given(parsers.parse('screening model "{run_id}" that {problem}'))
def broken_screening_model(world: World, run_id: str, problem: str) -> None:
    path = world["screening_models_dir"] / f"{run_id}.pt"
    if problem == "has no file":
        return
    if problem == "is not a readable model file":
        path.write_bytes(b"not a model")
        return
    leave_out, n_features = NOT_WHOLE[problem]
    validation = world["validation"]["1"]
    if problem.startswith("misses"):
        # Without its lowest threshold, the file's lowest misses one.
        validation = {key: counts for key, counts in validation.items() if key > 0.2}
    write_screening_model(
        path.parent,
        run_id,
        validation,
        NOW + timedelta(hours=1),
        leave_out=leave_out,
        n_features=n_features,
    )


@given(parsers.parse('the file of the deployed "{run_id}" has changed on disk'))
def changed_on_disk(world: World, run_id: str) -> None:
    deploy(world, run_id)
    with (world["screening_models_dir"] / f"{run_id}.pt").open("ab") as file:
        file.write(b"tampered")


@given(parsers.parse('laboratory staff member "{name}"'))
def staff_member(world: World, name: str) -> None:
    world["staff_member"] = make_laboratory_staff_member(name)


@when(parsers.parse('"{name}" tries to deploy screening model "{run_id}"'))
def staff_tries(
    world: World, client: Client, settings: Settings, name: str, run_id: str
) -> None:
    settings.SCREENING_MODELS_DIR = world["screening_models_dir"]
    client.force_login(world["staff_member"])
    client.post(reverse("deployment:deploy", kwargs={"run_id": run_id}))


def deployed(world: World) -> tuple[str, float] | None:
    """The run ID and threshold of the model that screens now, if one can."""
    from web.hospital.deployment.models import Deployment, Screener

    screener = Deployment.objects.screener(world["screening_models_dir"])
    if not isinstance(screener, Screener):
        return None
    return (
        screener.deployed_screening_model.run_id,
        screener.deployed_screening_model.threshold,
    )


def deployed_run(world: World) -> str | None:
    """The run ID of the model that screens now, if one can."""
    return None if (now := deployed(world)) is None else now[0]


def no_usable_model(world: World) -> object:
    from web.hospital.deployment.models import Deployment, Screener

    deployed = Deployment.objects.screener(world["screening_models_dir"])
    return None if isinstance(deployed, Screener) else deployed


@then("there is no deployed screening model")
def no_deployed_model(world: World) -> None:
    from web.hospital.deployment.models import NoUsableModel

    assert no_usable_model(world) is NoUsableModel.NO_DEPLOYED_MODEL


@then(parsers.parse('screening models "{first}" and "{second}" can be deployed'))
def can_be_deployed(world: World, first: str, second: str) -> None:
    from web.hospital.deployment.model_files import screening_models

    listed = {
        model.run_id: model for model in screening_models(world["screening_models_dir"])
    }
    assert {first, second} <= listed.keys()


def username(name: str) -> str:
    """The username make_user gives `name`."""
    return name.lower().replace(" ", "-")


@then("there is no target sensitivity")
def no_target(world: World) -> None:
    from web.hospital.deployment.models import TargetSensitivity

    assert TargetSensitivity.objects.current() is None


@then(parsers.parse('the target sensitivity is {percent:d}%, set by "{name}"'))
def target_is(world: World, percent: int, name: str) -> None:
    from web.hospital.deployment.models import TargetSensitivity

    target = TargetSensitivity.objects.current()
    assert target is not None
    assert (target.percent, target.set_by.username) == (percent, username(name))


@then(
    parsers.parse('setting it is refused with code "{code}" on the target sensitivity')
)
def target_refused(world: World, code: str) -> None:
    assert [error.code for error in world["error"].error_dict["percent"]] == [code]


@then(parsers.parse("the database refuses a target sensitivity of {percent:d}%"))
def database_refuses_target(world: World, percent: int) -> None:
    from django.db import IntegrityError, transaction

    from web.hospital.deployment.models import TargetSensitivity

    with pytest.raises(IntegrityError), transaction.atomic():
        TargetSensitivity.objects.create(
            percent=percent, set_at=NOW, set_by=world["director"]
        )


@then(
    parsers.parse(
        '"{run_id}" is the deployed screening model, at threshold {threshold:g},'
        ' for target {percent:d}%, deployed by "{name}"'
    )
)
def is_deployed(
    world: World, run_id: str, threshold: float, percent: int, name: str
) -> None:
    from web.hospital.deployment.models import Deployment

    assert deployed(world) == (run_id, threshold)
    latest = Deployment.objects.latest("deployed_at", "pk")
    assert (latest.target_sensitivity, latest.deployed_by.username) == (
        percent,
        username(name),
    )


@then(
    parsers.parse(
        "the deployment records local validation sensitivity {sensitivity} and"
        " specificity {specificity}"
    )
)
def records_validation(world: World, sensitivity: str, specificity: str) -> None:
    from web.hospital.deployment.models import Deployment

    latest = Deployment.objects.latest("deployed_at", "pk")
    counts = latest.deployed_screening_model.local_validation
    found, missed = counts["true_positives"], counts["false_negatives"]
    cleared, alarmed = counts["true_negatives"], counts["false_positives"]
    assert f"{found} of {found + missed}" == sensitivity
    assert f"{cleared} of {cleared + alarmed}" == specificity


@then(parsers.re(r"the deployment history lists (?P<entries>.+)$"))
def history(world: World, entries: str) -> None:
    from web.hospital.deployment.models import Deployment

    listed = [
        f'"{deployment.deployed_screening_model.run_id}"'
        f" at {deployment.deployed_screening_model.threshold:g}"
        f" for {deployment.target_sensitivity}%"
        for deployment in Deployment.objects.order_by("deployed_at", "pk")
    ]
    assert ", ".join(listed) == entries


@then(parsers.parse('deploying is refused with code "{code}"'))
def deploying_is_refused(world: World, code: str) -> None:
    assert world["error"].code == code


@then(
    parsers.re(
        r'(?:the screening models|they) show "(?P<run_id>[^"]+)", (?P<is_deployed>deployed, )?'
        r"at threshold (?P<threshold>[\d.]+) with sensitivity (?P<sensitivity>\d+ of \d+), specificity (?P<specificity>\d+ of \d+),"
        r" positive predictive value (?P<ppv>\d+ of \d+),"
        r" negative predictive value (?P<npv>\d+ of \d+), AUROC (?P<auroc>[\d.]+)"
    )
)
def shows_validation(
    world: World,
    run_id: str,
    is_deployed: str | None,
    threshold: str,
    sensitivity: str,
    specificity: str,
    ppv: str,
    npv: str,
    auroc: str,
) -> None:
    from web.hospital.deployment.model_files import screening_models

    (model,) = [
        m for m in screening_models(world["screening_models_dir"]) if m.run_id == run_id
    ]
    from web.hospital.deployment.models import TargetSensitivity

    target = TargetSensitivity.objects.current()
    assert target is not None
    row = model.at_target(target.percent)
    assert row.threshold == float(threshold)
    assert str(row.sensitivity) == sensitivity
    assert str(row.specificity) == specificity
    assert str(row.positive_predictive_value) == ppv
    assert str(row.negative_predictive_value) == npv
    assert model.local_auroc == pytest.approx(float(auroc))
    assert (deployed_run(world) == run_id) == bool(is_deployed)


@then(parsers.parse('screening model "{run_id}" is not listed'))
def not_listed(world: World, run_id: str) -> None:
    from web.hospital.deployment.model_files import screening_models

    listed = [model.run_id for model in screening_models(world["screening_models_dir"])]
    assert listed == ["2", "1"]


@then(
    parsers.parse('deploying screening model "{run_id}" is refused with code "{code}"')
)
def deploying_refused(world: World, run_id: str, code: str) -> None:
    world.pop("error", None)
    deploy(world, run_id)
    assert world["error"].code == code


@then(
    parsers.parse(
        'there is no usable deployed screening model, with reason code "{code}"'
    )
)
def no_usable(world: World, code: str) -> None:
    assert getattr(no_usable_model(world), "value", None) == code


@then("the Models page says the deployed screening model changed on disk")
def page_says_changed(world: World) -> None:
    assert "changed on disk" in str(getattr(no_usable_model(world), "label", ""))


# A threshold is a score of the test split, which may round to 0 or 1 exactly.
@pytest.mark.parametrize("threshold", [-0.01, 1.01])
def test_the_database_refuses_a_threshold_outside_zero_and_one(
    threshold: float,
) -> None:
    from django.db import IntegrityError, transaction

    from web.hospital.deployment.models import DeployedScreeningModel

    screening_model = DeployedScreeningModel(
        run_id="1", sha256="0" * 64, threshold=threshold
    )
    with pytest.raises(ValidationError) as refused:
        screening_model.full_clean()
    assert [error.code for error in refused.value.error_dict["__all__"]] == [
        "threshold_not_from_zero_to_one"
    ]
    with pytest.raises(IntegrityError), transaction.atomic():
        screening_model.save()


@given(parsers.parse("a measure of {part:d} of {whole:d}"), target_fixture="measure")
def measure(part: int, whole: int) -> object:
    from web.hospital.deployment.model_files import Ratio

    return Ratio(part, whole)


@then(parsers.parse("it reads {percent}, with a 95% confidence interval of {interval}"))
def reads_with_interval(measure: object, percent: str, interval: str) -> None:
    from web.hospital.deployment.model_files import Ratio

    assert isinstance(measure, Ratio)
    assert measure.percent == (None if percent == "none" else percent)
    assert measure.interval == (None if interval == "none" else interval)


@given(
    parsers.parse(
        "a local validation with AUROC {auroc:f} on {deficient:d} iron-deficient and"
        " {other:d} other past patients"
    ),
    target_fixture="auroc_interval",
)
def local_validation_counts(auroc: float, deficient: int, other: int) -> str:
    from web.hospital.deployment.model_files import LocalValidationAt, auroc_interval

    # Any threshold's counts hold every past patient of the validation.
    counts = {
        "true_positives": deficient,
        "false_negatives": 0,
        "false_positives": other,
        "true_negatives": 0,
    }
    return auroc_interval(auroc, LocalValidationAt(0.05, counts))


@then(parsers.parse("its AUROC has a 95% confidence interval of {interval}"))
def has_auroc_interval(auroc_interval: str, interval: str) -> None:
    assert auroc_interval == interval


@given(
    parsers.parse(
        "a local validation with AUROC {auroc:f} on {deficient:d} iron-deficient and"
        " {other:d} other past patients, and {federated:f} across hospitals"
    ),
    target_fixture="verification",
)
def local_validation_and_claim(
    auroc: float, deficient: int, other: int, federated: float
) -> object:
    from web.hospital.deployment.model_files import LocalValidationAt, verification

    counts = {
        "true_positives": deficient,
        "false_negatives": 0,
        "false_positives": other,
        "true_negatives": 0,
    }
    return verification(auroc, federated, LocalValidationAt(0.05, counts))


@then(parsers.parse('it says the screening model "{verdict}"'))
def says_verdict(verification: object, verdict: str) -> None:
    from web.hospital.deployment.model_files import Verification

    assert isinstance(verification, Verification)
    assert verification.label == verdict.capitalize()
