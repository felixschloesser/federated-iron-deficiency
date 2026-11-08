"""Scenarios: screening models as each hospital stores them
(features/hospital/screening_models.feature); and reading one back."""

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import torch
from pytest_bdd import given, parsers, scenarios, then, when

from ml.cohort import CBC_VARS, FEATURES
from ml.final_model import Net
from ml.inference import probability
from tests.conftest import World
from web.hospital.deployment.model_files import (
    ScreeningModel,
    read_screening_model,
    store_fetched,
    store_screening_model,
)

STORED_AT = datetime(2026, 10, 30, 9, 0, tzinfo=UTC)
FEDERATED_AUROC = 0.85
# Files only; declared like every party's scenario module.
pytestmark = pytest.mark.django_db


scenarios("hospital/screening_models.feature")


@pytest.fixture
def cohort() -> pd.DataFrame:
    """A small cohort with both labels, standing in for one hospital's."""
    rng = np.random.default_rng(0)
    frame = pd.DataFrame(rng.normal(size=(200, len(FEATURES))), columns=FEATURES)
    return frame.assign(iron_deficient=rng.integers(0, 2, size=200))


def store(directory: Path, cohort: pd.DataFrame, run_id: int) -> Path:
    torch.manual_seed(run_id)
    return store_screening_model(
        directory,
        run_id=run_id,
        state_dict=Net().state_dict(),
        cohort=cohort,
        federated_auroc=FEDERATED_AUROC,
        stored_at=STORED_AT,
    )


@given("a hospital's training cohort", target_fixture="hospital")
def hospital(tmp_path: Path, cohort: pd.DataFrame) -> World:
    return {"folder": tmp_path, "cohort": cohort, "error": None}


@given(
    parsers.parse(
        "the hospital stored the screening models of runs {first:d} and {second:d}"
    )
)
def stored_two(hospital: World, first: int, second: int) -> None:
    store(hospital["folder"], hospital["cohort"], run_id=first)
    store(hospital["folder"], hospital["cohort"], run_id=second)
    hospital["before"] = (hospital["folder"] / f"{first}.pt").read_bytes()


@given(
    parsers.parse(
        "the disk fills up while the screening model of run {run_id:d} is written"
    )
)
def disk_full(monkeypatch: pytest.MonkeyPatch, run_id: int) -> None:
    def save_half(contents: object, target: Path) -> None:
        Path(target).write_bytes(b"PK half a zip")
        raise OSError("disk full")

    monkeypatch.setattr(torch, "save", save_half)


@when(
    parsers.re(
        r"the hospital stores the screening model of run (?P<run_id>\d+)( again)?"
    )
)
def stores(hospital: World, run_id: str) -> None:
    try:
        hospital["path"] = store(hospital["folder"], hospital["cohort"], int(run_id))
    except (FileExistsError, OSError) as error:
        hospital["error"] = error


@then(parsers.re(r'the hospital holds "(?P<name>[^"]+)"$'))
def holds(hospital: World, name: str) -> None:
    assert hospital["path"] == hospital["folder"] / name
    assert [path.name for path in hospital["folder"].iterdir()] == [name]


@then(parsers.parse('the hospital holds "{first}" and "{second}"'))
def holds_two(hospital: World, first: str, second: str) -> None:
    assert sorted(path.name for path in hospital["folder"].iterdir()) == [first, second]


@then(
    "it holds the weights, standardization, run ID, when it was stored, "
    "the AUROC across hospitals and the local validation"
)
def holds_metadata(hospital: World) -> None:
    screening_model = torch.load(hospital["path"])
    assert set(screening_model) == {
        "state_dict",
        "mean",
        "std",
        "run_id",
        "stored_at",
        "federated_auroc",
        "confusion_matrices",
        "local_auroc",
    }
    assert screening_model["run_id"] == 11
    assert screening_model["stored_at"] == STORED_AT.isoformat()


@then("it holds no threshold")
def holds_no_threshold(hospital: World) -> None:
    screening_model = torch.load(hospital["path"])
    assert not any("threshold" in key for key in screening_model)


@then("storing it is refused")
def refused(hospital: World) -> None:
    assert isinstance(hospital["error"], FileExistsError)


@then("storing it fails")
def fails(hospital: World) -> None:
    assert isinstance(hospital["error"], OSError)
    assert str(hospital["error"]) == "disk full"


@then(parsers.parse('"{name}" is unchanged'))
def unchanged(hospital: World, name: str) -> None:
    assert (hospital["folder"] / name).read_bytes() == hospital["before"]


@then("the hospital holds no screening model")
def holds_none(hospital: World) -> None:
    assert list(hospital["folder"].iterdir()) == []


@then(
    "its local validation holds the four counts of its test split at each"
    " threshold from 0.05 to 0.95 in steps of 0.05"
)
def local_validation(hospital: World) -> None:
    matrices = torch.load(hospital["path"])["confusion_matrices"]
    assert sorted(matrices) == pytest.approx([step / 20 for step in range(1, 20)])
    for matrix in matrices.values():
        assert set(matrix) == {
            "true_positives",
            "false_negatives",
            "false_positives",
            "true_negatives",
        }
        # The test split is 20% of the cohort (ml.validation.load_data).
        assert sum(matrix.values()) == 40
    # A higher threshold suggests ferritin for no more women.
    suggested = [
        matrices[threshold]["true_positives"] + matrices[threshold]["false_positives"]
        for threshold in sorted(matrices)
    ]
    assert suggested == sorted(suggested, reverse=True)


@then("an AUROC")
def an_auroc(hospital: World) -> None:
    assert 0.0 <= torch.load(hospital["path"])["local_auroc"] <= 1.0


@then("its AUROC across hospitals is exactly the aggregate the ServerApp sent")
def only_aggregate(hospital: World) -> None:
    assert torch.load(hospital["path"])["federated_auroc"] == FEDERATED_AUROC


# Reading a stored screening model back, as the hospital's web app does.


def read(path: Path) -> ScreeningModel:
    file = read_screening_model(path.read_bytes())
    assert file is not None
    return file


def test_a_screening_model_screens_like_a_deployment(
    tmp_path: Path, cohort: pd.DataFrame
) -> None:
    file = read(store(tmp_path, cohort, run_id=11))
    cbc = {var: float(cohort[var].iloc[0]) for var in CBC_VARS}
    assert 0.0 <= probability(file.state_dict, file.mean, file.std, cbc, age=30) <= 1.0


def test_a_stored_screening_model_reads_back_whole(
    tmp_path: Path, cohort: pd.DataFrame
) -> None:
    file = read(store(tmp_path, cohort, run_id=11))
    assert file.run_id == "11"
    assert file.stored_at == STORED_AT
    assert file.federated_auroc == FEDERATED_AUROC
    assert len(file.local_validation) == 19
    assert 0.0 <= file.local_auroc <= 1.0


def test_a_file_that_is_no_model_reads_as_none(tmp_path: Path) -> None:
    assert read_screening_model(b"not a model") is None


def receive(hospital: World, run_id: int, as_run: int | None = None) -> Path:
    """The weights seeded by run_id, fetched as the screening model of as_run."""
    torch.manual_seed(run_id)
    return store_fetched(
        hospital["folder"],
        run_id=run_id if as_run is None else as_run,
        state_dict=Net().state_dict(),
        cohort=hospital["cohort"],
        federated_auroc=FEDERATED_AUROC,
        stored_at=STORED_AT,
    )


@given(parsers.parse("the hospital received the screening model of run {run_id:d}"))
def received(hospital: World, run_id: int) -> None:
    receive(hospital, run_id)
    hospital["before"] = (hospital["folder"] / f"{run_id}.pt").read_bytes()


@when(
    parsers.re(
        r"the hospital receives the screening model of run (?P<run_id>\d+)( again)?"
    )
)
def receives(hospital: World, run_id: str) -> None:
    try:
        hospital["path"] = receive(hospital, int(run_id))
    except OSError as error:
        hospital["error"] = error


@then("receiving it succeeds")
def receiving_succeeds(hospital: World) -> None:
    assert hospital["error"] is None


@when(
    parsers.parse(
        "the hospital receives other weights as the screening model of run {run_id:d}"
    )
)
def receives_other(hospital: World, run_id: int) -> None:
    try:
        hospital["path"] = receive(hospital, run_id + 1000, as_run=run_id)
    except FileExistsError as error:
        hospital["error"] = error


@then("receiving it is refused")
def receiving_refused(hospital: World) -> None:
    assert isinstance(hospital["error"], FileExistsError)
