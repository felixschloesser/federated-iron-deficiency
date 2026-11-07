"""Scenarios: the laboratory director fetches new final models, which the
hospital's web app validates locally, stores and acknowledges
(features/hospital/fetch.feature). The startup is a stand-in."""

from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import torch
from django.test import Client
from django.urls import reverse
from pytest_bdd import given, parsers, scenarios, then, when
from pytest_django.asserts import assertContains
from pytest_django.fixtures import Settings

from ml.cohort import FEATURES
from ml.final_model import FinalModel, Net, read, to_bytes
from shared.messaging import messages_pb2
from tests.conftest import World
from tests.hospital.conftest import make_laboratory_director
from tests.hospital.fake_startup import FakeStartup, running

FEDERATED = {"eval_auroc": 0.85}
# The stand-in serves from its own threads.
pytestmark = pytest.mark.django_db(transaction=True)

scenarios("hospital/fetch.feature")


def offered(run_id: str, seed: int) -> messages_pb2.FinalModel:
    """A released final model as the startup's endpoint sends it (DF33)."""
    torch.manual_seed(seed)
    return messages_pb2.FinalModel(
        run_id=run_id,
        weights=to_bytes(FinalModel(state_dict=Net().state_dict())),
        federated=FEDERATED,
    )


@pytest.fixture
def startup(settings: Settings) -> Iterator[FakeStartup]:
    fake = FakeStartup()
    with running(fake) as address:
        settings.STARTUP_ADDRESS = address
        settings.HOSPITAL_CERTIFICATE_NAME = "uz-leuven"
        yield fake


@given("a hospital's training cohort")
def training_cohort(
    world: World, settings: Settings, tmp_path: Path, startup: FakeStartup
) -> None:
    """The training cohort the hospital's web app validates on, as its laboratory
    director provided it."""
    from ml.training_cohort import write_training_cohort

    rng = np.random.default_rng(0)
    frame = pd.DataFrame(rng.normal(size=(200, len(FEATURES))), columns=FEATURES)
    frame = frame.assign(iron_deficient=rng.integers(0, 2, size=200))
    settings.TRAINING_COHORT_DIR = tmp_path / "cohort"
    write_training_cohort(frame, settings.TRAINING_COHORT_DIR)
    settings.SCREENING_MODELS_DIR = tmp_path / "screening-models"
    settings.SCREENING_MODELS_DIR.mkdir()
    world["startup"] = startup
    world["folder"] = settings.SCREENING_MODELS_DIR


@given(parsers.parse('the startup released final model "{run_id}"'))
def released(world: World, run_id: str) -> None:
    world["startup"].offered.append(offered(run_id, seed=1))


@given(
    parsers.parse('the startup offers final model "{run_id}" again, with other weights')
)
def offered_again(world: World, run_id: str) -> None:
    world["startup"].acknowledged.clear()
    world["startup"].offered[:] = [offered(run_id, seed=2)]
    world["before"] = (world["folder"] / f"{run_id}.pt").read_bytes()


@given("the startup cannot be reached")
def unreachable(settings: Settings) -> None:
    # A port nothing listens on.
    settings.STARTUP_ADDRESS = "127.0.0.1:1"


@given("the laboratory director fetched new final models")
@when("the laboratory director fetches new final models")
def director_fetches(world: World, client: Client) -> None:
    if "director" not in world:
        world["director"] = make_laboratory_director("Director One")
    client.force_login(world["director"])
    world["page"] = client.post(reverse("deployment:fetch_final_models"), follow=True)


@then("the hospital holds no final model")
def holds_none(world: World) -> None:
    assert list(world["folder"].iterdir()) == []


@then(
    parsers.parse(
        'the hospital holds "{name}" with its local validation and the AUROC across'
        " hospitals"
    )
)
def holds_validated(world: World, name: str) -> None:
    model = read(world["folder"] / name)
    assert model.problem() is None
    assert model.confusion_matrices
    assert model.local_auroc is not None
    assert model.federated == FEDERATED


@then(parsers.parse('the startup is told the hospital stored final model "{run_id}"'))
def acknowledged(world: World, run_id: str) -> None:
    assert world["startup"].acknowledged == [run_id]
    assert world["startup"].certificate_names == ["uz-leuven"]


@then(parsers.parse('"{name}" is unchanged'))
def unchanged(world: World, name: str) -> None:
    assert (world["folder"] / name).read_bytes() == world["before"]


@then("the page says the startup could not be reached")
def says_unreachable(world: World) -> None:
    assertContains(world["page"], "The startup could not be reached")


@given("the laboratory director has not provided a training cohort")
def no_training_cohort(settings: Settings) -> None:
    from ml.training_cohort import remove_training_cohort

    remove_training_cohort(settings.TRAINING_COHORT_DIR)


@then("the page says to provide the training cohort first")
def says_provide_first(world: World) -> None:
    assertContains(
        world["page"],
        "Provide the training cohort first: final models are validated on it.",
    )


@then("the startup is not asked")
def startup_not_asked(world: World) -> None:
    assert world["startup"].certificate_names == []
