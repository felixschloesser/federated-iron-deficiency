"""Scenarios: screening a CBC in the lab app with a deployed model
(features/hospital/screening.feature)."""

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest
import torch
from django.db.models import DecimalField, FloatField
from pytest_bdd import given, parsers, scenarios, then, when

from ml.cohort import CBC_VARS, FEATURES, eligible
from ml.final_model import (
    Net,
    model_file_path,
    standardization_tensor,
    write_contents,
)
from tests.conftest import World
from tests.hospital.conftest import make_practice
from web.hospital.analyser.models import Participant
from web.hospital.deployment.model_files import sha256
from web.hospital.deployment.models import Deployment
from web.hospital.lab.models import (
    LabOrderDetails,
    Sample,
    ScreeningResult,
    TestRequest,
    is_screened_indication,
)
from web.shared.vocabulary import ClinicalIndication, RegisteredSex
from web.shared.vocabulary import Test as OrderedTest

# Scenarios: screening a CBC when the analyser runs (features/hospital/screening.feature).

NOW = datetime(2026, 10, 30, 11, 0, tzinfo=UTC)
PRACTICE = "client"
# The test model reads this one CBC value: high scores above the threshold, 0 below.
DECIDING = CBC_VARS[0]
SIDES = {"above": 20.0, "below": 0.0}
pytestmark = pytest.mark.django_db

scenarios("hospital/screening.feature")


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


# Local validation at the thresholds the scenarios deploy at; the counts are not read.
CONFUSION_MATRICES = {
    threshold: {
        "true_positives": 7,
        "false_negatives": 3,
        "false_positives": 5,
        "true_negatives": 37,
    }
    for threshold in (0.4, 0.5)
}


def write_model(directory: Path, run_id: str, local_auroc: float) -> None:
    zeros = pd.Series(0.0, index=FEATURES)
    path = model_file_path(directory, run_id)
    path.unlink(missing_ok=True)  # "changed on disk" replaces the deployed file
    write_contents(
        path,
        {
            "state_dict": deciding_model(),
            "mean": standardization_tensor(zeros),
            "std": standardization_tensor(zeros + 1),
            "run_id": int(run_id),
            "stored_at": NOW.isoformat(),
            "federated_auroc": 0.87,
            "confusion_matrices": CONFUSION_MATRICES,
            "local_auroc": local_auroc,
        },
    )


@given(parsers.parse('screening model "{run_id}"'))
def screening_model(world: World, tmp_path: Path, run_id: str) -> None:
    world["screening_models_dir"] = tmp_path / "screening-models"
    write_model(world["screening_models_dir"], run_id, local_auroc=0.84)


@given(
    parsers.parse(
        'the laboratory director deployed "{run_id}" at threshold {threshold:g}'
    )
)
def deployed(world: World, run_id: str, threshold: float) -> None:
    Deployment.objects.deploy(
        run_id=run_id,
        threshold=threshold,
        directory=world["screening_models_dir"],
        now=NOW,
    )


@given("no screening model has been deployed")
def nothing_deployed() -> None:
    pass


@given(parsers.parse('the file of the deployed "{run_id}" has changed on disk'))
def changed_on_disk(world: World, run_id: str) -> None:
    deployed(world, run_id, threshold=0.5)
    write_model(world["screening_models_dir"], run_id, local_auroc=0.6)


def lab_sample(
    world: World,
    test: OrderedTest,
    clinical_indication: ClinicalIndication | None,
    sex: RegisteredSex,
    age: int,
) -> None:
    seqn = 100001
    Participant.objects.create(
        seqn=seqn, cbc={var: 0.0 for var in CBC_VARS}, ferritin=10.0
    )
    world["test_request"] = TestRequest.objects.receive(
        practice=make_practice(PRACTICE),
        details=LabOrderDetails(
            sample_id=str(seqn),
            test=test,
            clinical_indication=clinical_indication,
            registered_sex=sex,
            age=age,
            ordered_at=NOW,
        ),
    )


@given(parsers.parse("a CBC sample of a woman aged {age:d} for a screened indication"))
def eligible_cbc(world: World, age: int) -> None:
    lab_sample(
        world,
        OrderedTest.CBC,
        ClinicalIndication.SUSPECTED_ANAEMIA,
        RegisteredSex.FEMALE,
        age,
    )


@given(
    parsers.re(
        r"a CBC sample (?P<indication>for a screened indication"
        r"|for an indication not screened),"
        r" registered sex (?P<sex>\w+), aged (?P<age>\d+)"
    )
)
def cbc(world: World, indication: str, sex: str, age: str) -> None:
    chosen = (
        ClinicalIndication.SUSPECTED_ANAEMIA
        if indication == "for a screened indication"
        else ClinicalIndication.OTHER
    )
    lab_sample(world, OrderedTest.CBC, chosen, RegisteredSex(sex), int(age))


@given(parsers.parse("a ferritin sample of a woman aged {age:d}"))
def ferritin_sample(world: World, age: int) -> None:
    lab_sample(world, OrderedTest.FERRITIN, None, RegisteredSex.FEMALE, age)


@given(parsers.parse("the deployed model scores the sample {side} the threshold"))
def scores(world: World, side: str) -> None:
    Participant.objects.filter(seqn=int(world["test_request"].sample.sample_id)).update(
        cbc={var: SIDES[side] if var == DECIDING else 0.0 for var in CBC_VARS}
    )


@when("laboratory staff run the analyser")
def run_analyser(world: World) -> None:
    world["test_request"] = TestRequest.objects.get(
        pk=world["test_request"].pk
    ).run_analyser(
        directory=world["screening_models_dir"],
        now=NOW,
    )


def result_label(test_request: TestRequest) -> str:
    assert test_request.screening_result is not None
    return ScreeningResult(test_request.screening_result).label.lower()


@then(parsers.re(r'the screening result is "(?P<result>[^"]+)"$'))
def screening_result(world: World, result: str) -> None:
    assert result_label(world["test_request"]) == result


@then(parsers.parse('the screening result is "not screened" with reason "{reason}"'))
def not_screened(world: World, reason: str) -> None:
    test_request = world["test_request"]
    assert result_label(test_request) == "not screened"
    assert test_request.not_screened_reason == reason
    assert test_request.screened_by is None


@then("the sample is screened by the model")
def screened(world: World) -> None:
    test_request = world["test_request"]
    assert result_label(test_request) != "not screened"
    assert test_request.screened_by is not None


@then(
    parsers.parse(
        'the screening result records screening model "{run_id}",'
        " its SHA-256 and threshold {threshold:g}"
    )
)
def records_screening_model(world: World, run_id: str, threshold: float) -> None:
    screening_model = world["test_request"].screened_by
    assert screening_model.run_id == run_id
    path = model_file_path(world["screening_models_dir"], run_id)
    assert screening_model.sha256 == sha256(path.read_bytes())
    assert screening_model.threshold == threshold


@then("no stored field of the sample or its screening result holds a score")
def no_score(world: World) -> None:
    test_request = world["test_request"]
    for model in (TestRequest, Sample):
        for field in model._meta.concrete_fields:
            assert not isinstance(field, FloatField | DecimalField), field
    # The JSON results are the analyser's values only.
    tube = Participant.objects.get(seqn=int(test_request.sample.sample_id))
    assert test_request.results == tube.measure(OrderedTest.CBC)


@then("the sample has no screening result")
def no_screening_result(world: World) -> None:
    test_request = world["test_request"]
    assert test_request.screening_result is None
    assert test_request.not_screened_reason is None
    assert test_request.screened_by is None


@then(
    parsers.re(
        r"the lab report is released (?P<suggested>with|without) ferritin suggested"
    )
)
def released(world: World, suggested: str) -> None:
    (test_request,) = TestRequest.objects.reports_to_send(make_practice(PRACTICE))
    assert test_request.pk == world["test_request"].pk
    assert test_request.ferritin_suggested is (suggested == "with")


@pytest.mark.parametrize(
    "reason", ["not_eligible", "no_deployed_model", "deployed_model_changed"]
)
def test_every_reason_but_not_eligible_is_a_model_problem(reason: str) -> None:
    from web.hospital.deployment.models import NotScreened

    assert {choice.value for choice in NotScreened} == {
        "not_eligible",
        "no_deployed_model",
        "deployed_model_changed",
    }
    assert NotScreened(reason).is_model_problem() is (reason != "not_eligible")


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
    assert is_screened_indication(ClinicalIndication(indication)) is screened


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
    test_request = TestRequest(
        clinical_indication=ClinicalIndication.SUSPECTED_ANAEMIA,
        registered_sex=sex,
        age=age,
    )
    trained_on = eligible(pd.Series([sex.label]), pd.Series([age])).iloc[0]
    assert (test_request.not_eligible() is None) == trained_on
