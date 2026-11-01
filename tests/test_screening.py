"""Checks for local screening with a deployed model, and screening a CBC in the
lab app (features/screening.feature)."""

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest
import torch
from django.db.models import DecimalField, FloatField
from pytest_bdd import given, parsers, scenarios, then, when

from iron_deficiency.dataset import CBC_VARS, FEATURES
from iron_deficiency.screening import save_deployment, screen
from iron_deficiency.task import Net
from tests.conftest import World
from web.deployment import services as deployment_services
from web.deployment.domain import NoUsableModel, sha256
from web.lab import queries as lab_queries
from web.lab import services as lab_services
from web.lab.domain import NotScreened, ScreeningResult
from web.lab.models import LabOrder, Sample
from web.nhanes.models import Participant
from web.vocabulary import ClinicalIndication, RegisteredSex
from web.vocabulary import Test as OrderedTest


def test_screen_scores_only_eligible_women_and_returns_only_decisions(
    tmp_path: Path,
) -> None:
    model = tmp_path / "model.pt"
    zeros = pd.Series(0.0, index=FEATURES)
    save_deployment(model, Net().state_dict(), zeros, zeros + 1, threshold=0.5)
    samples = pd.DataFrame(
        {
            "sample_id": [1, 2, 3],
            "sex": ["Female", "Male", "Female"],
            "age": [30, 30, 60],
            **{var: [1.0] * 3 for var in CBC_VARS},
            "name": ["A", "B", "C"],  # A lab export may carry more than needed
        }
    )

    results = screen(samples, model)

    assert list(results.columns) == ["sample_id", "result"]
    assert results["result"].iat[0] in {"flagged", "not flagged"}
    assert results["result"].iloc[1:].tolist() == ["not screened"] * 2


# Scenarios: screening a CBC when the analyser runs (features/screening.feature).

NOW = datetime(2026, 10, 30, 11, 0, tzinfo=UTC)
CLIENT = "client"
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
    save_deployment(
        directory / f"{run_id}.pt", deciding_model(), zeros, zeros + 1, threshold
    )


@given(parsers.parse('screening model "{run_id}" with threshold {threshold:g}'))
def screening_model(
    world: World, tmp_path: Path, run_id: str, threshold: float
) -> None:
    world["final_models_dir"] = tmp_path / "final-models"
    write_model(world["final_models_dir"], run_id, threshold)


@given(parsers.parse('the laboratory director deployed "{run_id}"'))
def deployed(world: World, run_id: str) -> None:
    deployment_services.deploy(
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
    indication: ClinicalIndication | None,
    sex: RegisteredSex,
    age: int,
) -> None:
    seqn = 100001
    Participant.objects.create(
        seqn=seqn, cbc={var: 0.0 for var in CBC_VARS}, ferritin=10.0
    )
    world["lab_order"] = lab_services.record_lab_order(
        client=CLIENT,
        details=lab_services.LabOrderDetails(
            sample_id=str(seqn),
            test=test,
            indication=indication,
            registered_sex=sex,
            age=age,
            general_practitioner="Dr. Demo A",
            ordered_at=NOW,
        ),
    )


@given(
    parsers.parse(
        "a CBC sample of a woman aged {age:d} with indication unexplained fatigue"
    )
)
def eligible_cbc(world: World, age: int) -> None:
    lab_sample(
        world,
        OrderedTest.CBC,
        ClinicalIndication.UNEXPLAINED_FATIGUE,
        RegisteredSex.FEMALE,
        age,
    )


@given(
    parsers.re(
        r"a CBC sample with indication (?P<indication>[a-z -]+),"
        r" registered sex (?P<sex>\w+), aged (?P<age>\d+)"
    )
)
def cbc(world: World, indication: str, sex: str, age: str) -> None:
    lab_sample(
        world,
        OrderedTest.CBC,
        {choice.label.lower(): choice for choice in ClinicalIndication}[indication],
        RegisteredSex(sex),
        int(age),
    )


@given(parsers.parse("a ferritin sample of a woman aged {age:d}"))
def ferritin_sample(world: World, age: int) -> None:
    lab_sample(world, OrderedTest.FERRITIN, None, RegisteredSex.FEMALE, age)


@given(parsers.parse("the deployed model scores the sample {side} the threshold"))
def scores(world: World, side: str) -> None:
    Participant.objects.filter(seqn=int(world["lab_order"].sample.sample_id)).update(
        cbc={var: SIDES[side] if var == DECIDING else 0.0 for var in CBC_VARS}
    )


@when("laboratory staff run the analyser")
def run_analyser(world: World) -> None:
    world["lab_order"] = lab_services.run_analyser(
        lab_order=LabOrder.objects.get(pk=world["lab_order"].pk),
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
    assert screening_model.sha256 == sha256(world["final_models_dir"] / f"{run_id}.pt")
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
    (lab_order,) = lab_queries.lab_reports_to_send(CLIENT)
    assert lab_order.pk == world["lab_order"].pk
    assert lab_order.ferritin_suggested is (suggested == "with")


@pytest.mark.parametrize("reason", NoUsableModel)
def test_every_reason_without_a_usable_model_is_a_not_screened_reason(
    reason: NoUsableModel,
) -> None:
    assert NotScreened(reason) == reason.value


@pytest.mark.parametrize("reason", NotScreened)
def test_only_a_reason_without_a_usable_model_is_a_model_problem(
    reason: NotScreened,
) -> None:
    assert reason.is_model_problem() is (reason.value in NoUsableModel.values)


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
