"""The hospital's builders: its staff, the practices it knows, the lab orders
its endpoint records, its analyser stand-in, and final models as they arrive."""

from typing import TYPE_CHECKING

from ml.cohort import FEATURES
from tests.conftest import make_user
from tests.django_settings import _test_settings
from web.vocabulary import RegisteredSex

if TYPE_CHECKING:
    from datetime import datetime
    from pathlib import Path

    from web.accounts.models import User
    from web.hospital.lab.models import Practice, TestRequest
    from web.hospital.nhanes.models import Participant
    from web.vocabulary import Test

# The settings every test of this party runs with (tests/django_settings.py).
__all__ = ["_test_settings"]


def make_laboratory_staff_member(name: str) -> "User":
    from web.accounts.roles import Role

    return make_user(name, Role.LABORATORY_STAFF)


def make_laboratory_director(name: str) -> "User":
    from web.accounts.roles import Role

    return make_user(name, Role.LABORATORY_DIRECTOR)


def make_practice(certificate_name: str = "practice") -> "Practice":
    """A practice the hospital works with, by its certificate name."""
    from web.hospital.lab.models import Practice

    return Practice.objects.add(
        certificate_name=certificate_name, name=certificate_name.title()
    )


def make_tube() -> "Participant":
    """What a new patient's samples would measure at the hospital's analyser
    stand-in: placeholder CBC values, no ferritin. Its number starts their sample IDs."""
    from ml.cohort import CBC_VARS
    from web.hospital.nhanes.models import Participant

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
    """A lab order (DF23) as the hospital's messaging endpoint records it, from the
    practice make_practice() adds; a CBC for a screened indication."""
    from web.hospital.lab.models import LabOrderDetails, TestRequest

    return TestRequest.objects.receive(
        practice=make_practice(),
        details=LabOrderDetails(
            sample_id=sample_id,
            test=test,
            screened_indication=test.takes_indication(),
            registered_sex=sex,
            age=age,
            ordered_at=now,
        ),
    )


def write_final_model(
    directory: "Path",
    run_id: str,
    validation: dict[float, dict[str, int]],
    stored_at: "datetime",
    local_auroc: float = 0.84,
    leave_out: tuple[str, ...] = (),
    n_features: int = len(FEATURES),
) -> "Path":
    """A final model as the ClientApp stores it (ml.training),
    with `validation`, its confusion matrix at each threshold."""
    import torch

    from ml.final_model import Net

    contents = {
        "state_dict": Net(n_features=n_features).state_dict(),
        "mean": torch.zeros(len(FEATURES)),
        "std": torch.ones(len(FEATURES)),
        "run_id": run_id,
        "stored_at": stored_at.isoformat(),
        "federated": {"eval_auroc": 0.87},
        "confusion_matrices": validation,
        "local_auroc": local_auroc,
    }
    for key in leave_out:
        del contents[key]
    path = directory / f"{run_id}.pt"
    torch.save(contents, path)
    return path
