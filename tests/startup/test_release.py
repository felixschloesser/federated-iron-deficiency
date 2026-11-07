"""Scenarios: the startup releases final models and recipient hospitals fetch
them from its final-models endpoint, over gRPC, driven as a hospital's web app
would drive it (features/startup/release.feature)."""

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import grpc
import pytest
from django.test import Client
from django.urls import reverse
from django.utils.text import slugify
from google.protobuf.empty_pb2 import Empty
from pytest_bdd import given, parsers, scenarios, then, when
from pytest_django.asserts import assertContains
from pytest_django.fixtures import Settings

from tests.conftest import World
from tests.startup.conftest import make_data_scientist
from web.shared.messaging import messages_pb2, messages_pb2_grpc

NOW = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)
# The endpoint runs in its own threads, so the test may not hold a transaction.
pytestmark = pytest.mark.django_db(transaction=True)

scenarios("startup/release.feature")


@pytest.fixture
def startup(settings: Settings, tmp_path: Path) -> Iterator[str]:
    """The startup's final-models endpoint, running, over its final models; its
    address."""
    from web.startup.training.messaging import serve

    settings.FINAL_MODELS_DIR = tmp_path / "final-models"
    server, port = serve("127.0.0.1:0")
    yield f"127.0.0.1:{port}"
    server.stop(grace=None)


@given(
    parsers.parse(
        'the startup kept final model "{run_id}" with AUROC across hospitals {auroc:f}'
    )
)
def kept(
    world: World, startup: str, settings: Settings, run_id: str, auroc: float
) -> None:
    from ml.final_model import Net
    from ml.training import keep_final_model

    world["startup"] = startup
    keep_final_model(
        settings.FINAL_MODELS_DIR,
        run_id=int(run_id),
        state_dict=Net().state_dict(),
        federated={"eval_auroc": auroc},
        run_configuration={"num-server-rounds": 3, "batch-size": 64},
        stored_at=NOW,
    )


@given(parsers.parse('the startup knows hospital "{name}"'))
def knows_hospital(name: str) -> None:
    """The startup registered the hospital by its name."""
    from web.startup.training.models import Recipient

    Recipient.objects.add(name=name)


@when(parsers.parse('the startup registers hospital "{name}"'))
def registers_hospital(world: World, name: str) -> None:
    from django.core.exceptions import ValidationError

    from web.startup.training.models import Recipient

    try:
        Recipient.objects.add(name=name)
    except ValidationError as error:
        world["refused"] = error


@then("registering is refused as a slug taken")
def refused_slug_taken(world: World) -> None:
    from web.startup.training.models import Recipient

    refused = world["refused"].error_dict.values()
    assert [error.code for errors in refused for error in errors] == ["slug_taken"]
    assert Recipient.objects.count() == 1


@given(parsers.parse('data scientist "{name}" released final model "{run_id}"'))
@when(parsers.parse('data scientist "{name}" releases final model "{run_id}"'))
def releases(world: World, name: str, run_id: str) -> None:
    from web.startup.training.models import Release

    world["data_scientist"] = make_data_scientist(name)
    Release.objects.release(
        final_model_run_id=run_id, released_by=world["data_scientist"], now=NOW
    )


@then(parsers.parse('final model "{run_id}" is released by "{name}"'))
def released_by(world: World, run_id: str, name: str) -> None:
    from web.startup.training.models import Release

    release = Release.objects.get(final_model_run_id=run_id)
    assert release.released_by == world["data_scientist"]
    assert release.released_at == NOW


def call(world: World, method: str, request: Any, hospital: str | None) -> Any:
    """One call of the endpoint, as a hospital's web app makes it, named by its
    name's slug in the call's metadata; a refusal is kept."""
    metadata = () if hospital is None else (("party", slugify(hospital)),)
    with grpc.insecure_channel(world["startup"]) as channel:
        endpoint = messages_pb2_grpc.FinalModelsStub(channel)
        try:
            return getattr(endpoint, method)(request, timeout=10, metadata=metadata)
        except grpc.RpcError as error:
            world["refused"] = error
            return None


@when(parsers.parse('"{hospital}" fetches new final models'))
def fetches(world: World, hospital: str) -> None:
    world["fetched"] = call(world, "FetchNewFinalModels", Empty(), hospital)


@when("a hospital fetches new final models without naming itself")
def fetches_unnamed(world: World) -> None:
    world["fetched"] = call(world, "FetchNewFinalModels", Empty(), None)


@given(
    parsers.parse(
        '"{hospital}" fetched new final models and acknowledged final model "{run_id}"'
    )
)
def fetched_and_acknowledged(world: World, hospital: str, run_id: str) -> None:
    fetches(world, hospital)
    call(
        world,
        "AcknowledgeFinalModels",
        messages_pb2.FinalModelAcknowledgement(run_ids=[run_id]),
        hospital,
    )


@then("it receives no final model")
def receives_none(world: World) -> None:
    assert list(world["fetched"].final_models) == []


@then(
    parsers.parse(
        'it receives final model "{run_id}" with its weights and AUROC across'
        " hospitals {auroc:f}"
    )
)
def receives(world: World, run_id: str, auroc: float) -> None:
    from ml.final_model import Net, from_bytes

    (model,) = world["fetched"].final_models
    assert model.run_id == int(run_id)
    state_dict = from_bytes(model.weights).state_dict
    assert state_dict is not None
    assert state_dict.keys() == Net().state_dict().keys()
    assert model.federated["eval_auroc"] == pytest.approx(auroc)


@then("it receives no run configuration")
def no_run_configuration(world: World) -> None:
    from ml.final_model import from_bytes

    (model,) = world["fetched"].final_models
    assert from_bytes(model.weights).run_configuration == {}
    fields = {field.name for field in messages_pb2.FinalModel.DESCRIPTOR.fields}
    assert fields == {"run_id", "weights", "federated"}


@then("fetching is refused as unknown hospital")
def refused_unknown(world: World) -> None:
    error = world["refused"]
    assert error.code() == grpc.StatusCode.PERMISSION_DENIED
    assert error.details() == "unknown_hospital"


@then("fetching is refused as naming no hospital")
def refused_unnamed(world: World) -> None:
    error = world["refused"]
    assert error.code() == grpc.StatusCode.UNAUTHENTICATED
    assert error.details() == "hospital_required"


@when("the data scientist opens the final models")
def opens_final_models(world: World, client: Client) -> None:
    client.force_login(world["data_scientist"])
    world["page"] = client.get(reverse("training:models"))


@then(parsers.parse('final model "{run_id}" shows "{shown}"'))
def final_model_shows(world: World, run_id: str, shown: str) -> None:
    assertContains(world["page"], shown)
