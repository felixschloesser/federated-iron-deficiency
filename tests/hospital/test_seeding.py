"""The hospital's demo data (python -m demo.seed hospital): its staff, and what its analyser
stand-in measures for each NHANES participant it was given."""

from pathlib import Path

import pytest
from pytest_django.fixtures import Settings

from demo.seed import main
from ml.cohort import CBC_VARS
from tests.conftest import PEOPLE, write_extracts
from web.hospital.analyser.models import Participant
from web.shared.accounts.models import User
from web.shared.accounts.roles import Role, role_of

pytestmark = pytest.mark.django_db


@pytest.fixture
def extract(settings: Settings, tmp_path: Path) -> Path:
    """The hospital's folder of nhanes-download's extracts, in development."""
    settings.DEBUG = True
    hospital, _ = write_extracts(tmp_path)
    return hospital


def seeding(folder: Path, lab_records: Path | None = None) -> list[str]:
    """demo.seed's arguments for the hospital, from its extracts."""
    records = lab_records or folder / "lab-records.csv"
    return [
        "hospital",
        "--rows",
        str(folder / "participants.csv"),
        "--lab-records",
        str(records),
    ]


@pytest.fixture
def seeded(extract: Path) -> None:
    main(seeding(extract))


def test_seeds_its_staff(seeded: None) -> None:
    assert {role_of(user) for user in User.objects.all()} == {
        Role.LABORATORY_STAFF,
        Role.LABORATORY_DIRECTOR,
        None,  # no-role: for the refusal at login
    }
    assert User.objects.get(username="staff").check_password("demo-pass-2026")


# The pool: the two groups of eligible women with ferritin, 20 each.
POOL = 2 * 20


def test_seeds_every_eligible_woman_with_ferritin(seeded: None) -> None:
    """Men, women outside 18–49 and women without ferritin are not in the pool
    (demo/seeding/participants.py)."""
    assert Participant.objects.count() == POOL
    for group, (_, _, ferritin) in enumerate(PEOPLE[:2]):
        participants = Participant.objects.filter(
            seqn__range=(1000 + 100 * group, 1099 + 100 * group)
        )
        assert participants.count() == 20
        for participant in participants:
            assert participant.ferritin == ferritin
            assert participant.cbc == dict.fromkeys(CBC_VARS, float(group))


def test_running_twice_changes_nothing(seeded: None, extract: Path) -> None:
    main(seeding(extract))
    assert User.objects.count() == 3
    assert Participant.objects.count() == POOL


def test_refuses_outside_development(settings: Settings, extract: Path) -> None:
    settings.DEBUG = False
    with pytest.raises(SystemExit, match="DJANGO_DEBUG=1"):
        main(seeding(extract))
    assert not User.objects.exists()


def test_eligible_women_without_ferritin_are_never_seeded(seeded: None) -> None:
    assert not Participant.objects.filter(seqn__range=(1400, 1499)).exists()


def lab_records_file(tmp_path: Path, deficient: int, sound: int) -> Path:
    """A lab-records CSV as prepare writes it: eligible women, and one man."""
    import pandas as pd

    rows = [("Female", 30, 8.0)] * deficient + [("Female", 30, 40.0)] * sound
    rows += [("Male", 30, 40.0)]
    frame = pd.DataFrame(rows, columns=["sex", "age", "LBXFER"]).assign(
        CRP=1.0, pregnant=False
    )
    for number, var in enumerate(CBC_VARS):
        frame[var] = [float(row + number) for row in range(len(frame))]
    path = tmp_path / "lab-records.csv"
    frame.to_csv(path, index=False)
    return path


def test_a_hospital_seeds_its_lab_records(
    settings: Settings, tmp_path: Path, extract: Path
) -> None:
    from web.hospital.cohort.models import LabRecord, TrainingCohort

    settings.TRAINING_COHORT_DIR = tmp_path / "cohort"
    path = lab_records_file(tmp_path, deficient=20, sound=100)
    main(seeding(extract, path))
    main(seeding(extract, path))
    # Once, however often prepare runs; nothing provided without --provide.
    assert LabRecord.objects.count() == 121
    assert TrainingCohort.objects.provided() is None


def test_a_hospital_seeding_with_provide_provides_its_training_cohort(
    settings: Settings, tmp_path: Path, extract: Path
) -> None:
    """Through the laboratory director's own provide
    (features/hospital/training_cohort.feature); once, however often prepare runs."""
    from web.hospital.cohort.models import TrainingCohort

    settings.TRAINING_COHORT_DIR = tmp_path / "cohort"
    path = lab_records_file(tmp_path, deficient=20, sound=100)
    for _ in range(2):
        main([*seeding(extract, path), "--provide"])
    provided = TrainingCohort.objects.provided()
    assert provided is not None
    assert (provided.past_patients, provided.iron_deficient) == (120, 20)
    assert provided.provided_by.username == "director"
