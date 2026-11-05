"""Scenarios: screening a CBC in the lab app with a deployed model
(features/screening.feature)."""

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest
import torch
from django.db.models import DecimalField, FloatField
from pytest_bdd import given, parsers, scenarios, then, when

from iron_deficiency.cohort import CBC_VARS, FEATURES, eligible
from iron_deficiency.screening import (
    FinalModel,
    final_model_path,
    standardization_tensor,
    write,
)
from iron_deficiency.task import Net
from tests.conftest import World
from web.deployment.model_files import sha256
from web.deployment.models import Deployment, NoUsableModel
from web.lab.models import (
    LabOrder,
    LabOrderDetails,
    NotScreened,
    Sample,
    ScreeningResult,
)
from web.nhanes.models import Participant
from web.vocabulary import ClinicalIndication, RegisteredSex
from web.vocabulary import Test as OrderedTest

# Scenarios: screening a CBC when the analyser runs (features/screening.feature).

NOW = datetime(2026, 10, 30, 11, 0, tzinfo=UTC)
PRACTICE = "client"
# The test model reads this one CBC value: high scores above the threshold, 0 below.
DECIDING = CBC_VARS[0]
SIDES = {"above": 20.0, "below": 0.0}
pytestmark = pytest.mark.django_db

scenarios("screening.feature")


def deciding_model() -> dict[str, torch.Tensor]:
    """Weights whose probability is sigmoid(DECIDING - 10): far from 0.5 either way."""
    state = {
        name: torch.zeros_like(value) for name, value in Net().state_dict().items()
    }
    state["net.0.weight"][0, FEATURES.index(DECIDING)] = 1.0
    state["net.3.weight"][0, 0] = 1.0
    state["net.6.weight"][0, 0] = 1.0
    state["net.6.bias"][0] = -10.0
    return state


def write_model(directory: Path, run_id: str, threshold: float) -> None:
    zeros = pd.Series(0.0, index=FEATURES)
    path = final_model_path(directory, run_id)
    path.unlink(missing_ok=True)  # "changed on disk" replaces the deployed file
    write(
        path,
        FinalModel(
            state_dict=deciding_model(),
            mean=standardization_tensor(zeros),
            std=standardization_tensor(zeros + 1),
            threshold=threshold,
        ),
    )


@given(parsers.parse('screening model "{run_id}" with threshold {threshold:g}'))
def screening_model(
    world: World, tmp_path: Path, run_id: str, threshold: float
) -> None:
    world["final_models_dir"] = tmp_path / "final-models"
    write_model(world["final_models_dir"], run_id, threshold)


@given(parsers.parse('the laboratory director deployed "{run_id}"'))
def deployed(world: World, run_id: str) -> None:
    Deployment.objects.deploy(
        run_id=run_id, directory=world["final_models_dir"], now=NOW
    )


@given("no screening model has been deployed")
def nothing_deployed() -> None:
    pass


@given(parsers.parse('the file of the deployed "{run_id}" has changed on disk'))
def changed_on_disk(world: World, run_id: str) -> None:
    deployed(world, run_id)
    write_model(world["final_models_dir"], run_id, threshold=0.6)


def lab_sample(
    world: World,
    test: OrderedTest,
    screened_indication: bool,
    sex: RegisteredSex,
    age: int,
) -> None:
    seqn = 100001
    Participant.objects.create(
        seqn=seqn, cbc={var: 0.0 for var in CBC_VARS}, ferritin=10.0
    )
    world["lab_order"] = LabOrder.objects.record(
        practice=PRACTICE,
        details=LabOrderDetails(
            sample_id=str(seqn),
            test=test,
            screened_indication=screened_indication,
            registered_sex=sex,
            age=age,
            ordered_at=NOW,
        ),
    )


@given(parsers.parse("a CBC sample of a woman aged {age:d} for a screened indication"))
def eligible_cbc(world: World, age: int) -> None:
    lab_sample(world, OrderedTest.CBC, True, RegisteredSex.FEMALE, age)


@given(
    parsers.re(
        r"a CBC sample (?P<indication>for a screened indication"
        r"|for an indication not screened),"
        r" registered sex (?P<sex>\w+), aged (?P<age>\d+)"
    )
)
def cbc(world: World, indication: str, sex: str, age: str) -> None:
    screened = indication == "for a screened indication"
    lab_sample(world, OrderedTest.CBC, screened, RegisteredSex(sex), int(age))


@given(parsers.parse("a ferritin sample of a woman aged {age:d}"))
def ferritin_sample(world: World, age: int) -> None:
    lab_sample(world, OrderedTest.FERRITIN, False, RegisteredSex.FEMALE, age)


@given(parsers.parse("the deployed model scores the sample {side} the threshold"))
def scores(world: World, side: str) -> None:
    Participant.objects.filter(seqn=int(world["lab_order"].sample.sample_id)).update(
        cbc={var: SIDES[side] if var == DECIDING else 0.0 for var in CBC_VARS}
    )


@when("laboratory staff run the analyser")
def run_analyser(world: World) -> None:
    world["lab_order"] = LabOrder.objects.get(pk=world["lab_order"].pk).run_analyser(
        directory=world["final_models_dir"],
        now=NOW,
    )


def result_label(lab_order: LabOrder) -> str:
    assert lab_order.screening_result is not None
    return ScreeningResult(lab_order.screening_result).label.lower()


@then(parsers.re(r'the screening result is "(?P<result>[^"]+)"$'))
def screening_result(world: World, result: str) -> None:
    assert result_label(world["lab_order"]) == result


@then(parsers.parse('the screening result is "not screened" with reason "{reason}"'))
def not_screened(world: World, reason: str) -> None:
    lab_order = world["lab_order"]
    assert result_label(lab_order) == "not screened"
    assert lab_order.not_screened_reason == reason
    assert lab_order.screened_by is None


@then("the sample is screened by the model")
def screened(world: World) -> None:
    lab_order = world["lab_order"]
    assert result_label(lab_order) != "not screened"
    assert lab_order.screened_by is not None


@then(
    parsers.parse(
        'the screening result records screening model "{run_id}",'
        " its SHA-256 and threshold {threshold:g}"
    )
)
def records_final_model(world: World, run_id: str, threshold: float) -> None:
    screening_model = world["lab_order"].screened_by
    assert screening_model.run_id == run_id
    path = final_model_path(world["final_models_dir"], run_id)
    assert screening_model.sha256 == sha256(path.read_bytes())
    assert screening_model.threshold == threshold


@then("no stored field of the sample or its screening result holds a score")
def no_score(world: World) -> None:
    lab_order = world["lab_order"]
    for model in (LabOrder, Sample):
        for field in model._meta.concrete_fields:
            assert not isinstance(field, FloatField | DecimalField), field
    # The JSON results are the analyser's values only.
    tube = Participant.objects.get(seqn=int(lab_order.sample.sample_id))
    assert lab_order.results == tube.measure(OrderedTest.CBC)


@then("the sample has no screening result")
def no_screening_result(world: World) -> None:
    lab_order = world["lab_order"]
    assert lab_order.screening_result is None
    assert lab_order.not_screened_reason is None
    assert lab_order.screened_by is None


@then(
    parsers.re(
        r"the lab report is released (?P<suggested>with|without) ferritin suggested"
    )
)
def released(world: World, suggested: str) -> None:
    (lab_order,) = LabOrder.objects.reports_to_send(PRACTICE)
    assert lab_order.pk == world["lab_order"].pk
    assert lab_order.ferritin_suggested is (suggested == "with")


@pytest.mark.parametrize("reason", NoUsableModel)
def test_every_reason_without_a_usable_model_is_a_not_screened_reason(
    reason: NoUsableModel,
) -> None:
    assert NotScreened.because(reason).is_model_problem()


@pytest.mark.parametrize("reason", NotScreened)
def test_only_a_reason_without_a_usable_model_is_a_model_problem(
    reason: NotScreened,
) -> None:
    is_because = any(NotScreened.because(each) is reason for each in NoUsableModel)
    assert reason.is_model_problem() is is_because


@pytest.mark.parametrize(
    ("indication", "screened"),
    [
        ("suspected_anaemia", True),
        ("suspected_ibs", True),
        ("unexplained_fatigue", True),
        ("start_of_pregnancy", False),
        ("ckd_follow_up", False),
        ("other", False),
    ],
)
def test_screened_indications_are_where_the_guidelines_order_a_cbc_without_ferritin(
    indication: str, screened: bool
) -> None:
    assert ClinicalIndication(indication).is_screened() is screened


def test_every_indication_is_answered() -> None:
    assert {choice.value for choice in ClinicalIndication} == {
        "suspected_anaemia",
        "suspected_ibs",
        "unexplained_fatigue",
        "start_of_pregnancy",
        "ckd_follow_up",
        "other",
    }


@pytest.mark.parametrize("sex", RegisteredSex)
@pytest.mark.parametrize("age", [17, 18, 49, 50])
def test_the_lab_screens_exactly_whom_the_model_was_trained_on(
    sex: RegisteredSex, age: int
) -> None:
    lab_order = LabOrder(screened_indication=True, registered_sex=sex, age=age)
    trained_on = eligible(pd.Series([sex.label]), pd.Series([age])).iloc[0]
    assert (lab_order.not_eligible() is None) == trained_on
