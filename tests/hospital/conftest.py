"""The hospital's builders: its staff, the practices it knows, the lab orders
its endpoint records, its analyser stand-in, and screening models as they arrive."""

from typing import TYPE_CHECKING

from ml.cohort import FEATURES
from tests.conftest import make_user
from tests.django_settings import _test_settings
from web.shared.vocabulary import ClinicalIndication, RegisteredSex

if TYPE_CHECKING:
    from datetime import datetime
    from pathlib import Path

    import pandas as pd

    from web.hospital.analyser.models import Participant
    from web.hospital.lab.models import Practice, TestRequest
    from web.shared.accounts.models import User
    from web.shared.vocabulary import Test

# The settings every test of this party runs with (tests/django_settings.py).
__all__ = ["_test_settings"]


def make_laboratory_staff_member(name: str) -> "User":
    from web.shared.accounts.roles import Role

    return make_user(name, Role.LABORATORY_STAFF)


def make_laboratory_director(name: str) -> "User":
    from web.shared.accounts.roles import Role

    return make_user(name, Role.LABORATORY_DIRECTOR)


def make_practice(name: str = "Practice") -> "Practice":
    """A practice the hospital works with, by its name."""
    from web.hospital.lab.models import Practice

    return Practice.objects.add(name=name)


def make_tube() -> "Participant":
    """What a new patient's samples would measure at the hospital's analyser
    stand-in: placeholder CBC values, no ferritin. Its number starts their sample IDs."""
    from ml.cohort import CBC_VARS
    from web.hospital.analyser.models import Participant

    return Participant.objects.create(
        seqn=Participant.objects.count() + 1, cbc=dict.fromkeys(CBC_VARS, 1.0)
    )


def receive_lab_order(
    sample_id: str,
    test: "Test",
    now: "datetime",
    sex: "RegisteredSex" = RegisteredSex.FEMALE,
    age: int = 32,
) -> "TestRequest":
    """A lab order (DF23) as the hospital's lab-order endpoint records it, from the
    practice make_practice() adds; a CBC for a screened indication."""
    from web.hospital.lab.models import LabOrderDetails, TestRequest

    return TestRequest.objects.receive(
        practice=make_practice(),
        details=LabOrderDetails(
            sample_id=sample_id,
            test=test,
            clinical_indication=ClinicalIndication.SUSPECTED_ANAEMIA
            if test.takes_indication()
            else None,
            registered_sex=sex,
            age=age,
            ordered_at=now,
        ),
    )


def write_screening_model(
    directory: "Path",
    run_id: str,
    validation: dict[float, dict[str, int]],
    stored_at: "datetime",
    local_auroc: float = 0.84,
    leave_out: tuple[str, ...] = (),
    n_features: int = len(FEATURES),
) -> "Path":
    """A screening model as the hospital stores it (model_files.py),
    with `validation`, its confusion matrix at each threshold."""
    import torch

    from ml.final_model import Net

    contents = {
        "state_dict": Net(n_features=n_features).state_dict(),
        "mean": torch.zeros(len(FEATURES)),
        "std": torch.ones(len(FEATURES)),
        "run_id": run_id,
        "stored_at": stored_at.isoformat(),
        "federated_auroc": 0.87,
        "confusion_matrices": validation,
        "local_auroc": local_auroc,
    }
    for key in leave_out:
        del contents[key]
    path = directory / f"{run_id}.pt"
    torch.save(contents, path)
    return path


def make_lab_records(
    count: int,
    iron_deficient: int = 0,
    sex: "RegisteredSex" = RegisteredSex.FEMALE,
    age: int = 30,
    with_ferritin: bool = True,
    indication: ClinicalIndication = ClinicalIndication.SUSPECTED_ANAEMIA,
    crp: float | None = 1.0,
    ferritin: float | None = None,
) -> None:
    """`count` past patients' lab records, the first `iron_deficient` with ferritin
    below the cutoff; each CBC differs, so each record does."""
    from ml.cohort import CBC_VARS
    from web.hospital.cohort.models import LabRecord

    start = LabRecord.objects.count()
    LabRecord.objects.bulk_create(
        LabRecord(
            registered_sex=sex,
            age=age,
            cbc=dict.fromkeys(CBC_VARS, float(start + number)),
            ferritin=(
                ferritin
                if ferritin is not None
                else (8.0 if number < iron_deficient else 40.0)
            )
            if with_ferritin
            else None,
            clinical_indication=indication,
            crp=crp,
        )
        for number in range(count)
    )


def found_cohort(directory: "Path") -> "pd.DataFrame | None":
    """The training cohort as the startup's code at the hospital finds it in its
    folder, or None when it finds none."""
    import pandas as pd

    from ml.training_cohort import COHORT_FILE

    training_cohorts = (
        [path for path in directory.iterdir() if path.is_dir()]
        if directory.is_dir()
        else []
    )
    if not training_cohorts:
        return None
    (training_cohort,) = training_cohorts
    return pd.read_parquet(training_cohort / COHORT_FILE)
