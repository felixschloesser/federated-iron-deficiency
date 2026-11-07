"""The hospital's demo data (python -m demo.seed hospital): its staff, and what its analyser
stand-in measures for each NHANES participant it was given."""

from pathlib import Path

import pytest
from pytest_django.fixtures import Settings

from demo.seed import main
from demo.seeding import participants as seeding
from hospital.analyser.models import MADE_UP_FERRITIN, Participant
from ml.cohort import CBC_VARS
from shared.accounts.models import User
from shared.accounts.roles import Role, role_of
from shared.vocabulary import RESULT_NAMES
from shared.vocabulary import Test as OrderedTest
from tests.conftest import PEOPLE, nhanes_rows

pytestmark = pytest.mark.django_db


@pytest.fixture
def development(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    settings.DEBUG = True
    monkeypatch.setattr(seeding, "load_nhanes", nhanes_rows)


@pytest.fixture
def seeded(development: None) -> None:
    main(["hospital"])


def test_seeds_its_staff(seeded: None) -> None:
    assert {role_of(user) for user in User.objects.all()} == {
        Role.LABORATORY_STAFF,
        Role.LABORATORY_DIRECTOR,
        None,  # no-role: for the refusal at login
    }
    assert User.objects.get(username="staff").check_password("demo-pass-2026")


def test_seeds_three_participants_of_each_group_from_nhanes(seeded: None) -> None:
    assert Participant.objects.count() == 3 * len(PEOPLE)
    for group, (_, _, ferritin) in enumerate(PEOPLE):
        participants = Participant.objects.filter(
            seqn__range=(1000 + 10 * group, 1009 + 10 * group)
        )
        assert participants.count() == 3
        for participant in participants:
            assert participant.ferritin == ferritin
            # NHANES did not measure them: a value made up from the women who
            # were, at or above the cutoff (here the 25-year-olds' 40.0).
            assert participant.made_up_ferritin == (40.0 if ferritin is None else None)
            assert participant.cbc == dict.fromkeys(CBC_VARS, float(group))


def test_running_twice_changes_nothing(seeded: None) -> None:
    main(["hospital"])
    assert User.objects.count() == 3
    assert Participant.objects.count() == 3 * len(PEOPLE)


def test_refuses_outside_development(settings: Settings) -> None:
    settings.DEBUG = False
    with pytest.raises(SystemExit, match="DJANGO_DEBUG=1"):
        main(["hospital"])
    assert not User.objects.exists()


def test_reads_participants_from_a_csv(settings: Settings, tmp_path: Path) -> None:
    settings.DEBUG = True
    csv = tmp_path / "nhanes.csv"
    nhanes_rows().to_csv(csv, index=False)
    main(["hospital", "--nhanes", str(csv)])
    assert Participant.objects.count() == 3 * len(PEOPLE)


def test_eligible_women_without_ferritin_are_never_seeded(seeded: None) -> None:
    assert not Participant.objects.filter(seqn__range=(1040, 1049)).exists()


def test_the_number_of_participants_is_a_parameter(development: None) -> None:
    main(["hospital", "--patients", "6"])
    assert Participant.objects.count() == 6


def test_a_made_up_ferritin_is_reported_under_its_own_name() -> None:
    participant = Participant(seqn=1, cbc={}, ferritin=None, made_up_ferritin=60.0)
    assert participant.measure(OrderedTest.FERRITIN) == {MADE_UP_FERRITIN: 60.0}
    assert RESULT_NAMES[MADE_UP_FERRITIN].name == "Ferritin (made up for the demo)"
    assert RESULT_NAMES[MADE_UP_FERRITIN].unit == "ng/mL"


def lab_records_file(tmp_path: Path, deficient: int, sound: int) -> Path:
    """A lab-records CSV as prepare writes it: eligible women, and one man."""
    import pandas as pd

    rows = [("Female", 30, 8.0)] * deficient + [("Female", 30, 40.0)] * sound
    rows += [("Male", 30, 40.0)]
    frame = pd.DataFrame(rows, columns=["sex", "age", "LBXFER"])
    for number, var in enumerate(CBC_VARS):
        frame[var] = [float(row + number) for row in range(len(frame))]
    path = tmp_path / "lab-records.csv"
    frame.to_csv(path, index=False)
    return path


def test_a_hospital_seeds_its_lab_records(settings: Settings, tmp_path: Path) -> None:
    from hospital.cohort.models import LabRecord, TrainingCohort

    settings.DEBUG = True
    settings.TRAINING_COHORT_DIR = tmp_path / "cohort"
    path = lab_records_file(tmp_path, deficient=20, sound=100)
    main(["lab-records", "--csv", str(path)])
    main(["lab-records", "--csv", str(path)])
    # Once, however often prepare runs; nothing provided without --provide.
    assert LabRecord.objects.count() == 121
    assert TrainingCohort.objects.provided() is None


def test_a_hospital_seeding_with_provide_provides_its_training_cohort(
    settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Through the laboratory director's own provide
    (features/hospital/training_cohort.feature); once, however often prepare runs."""
    from hospital.cohort.models import TrainingCohort

    settings.DEBUG = True
    settings.TRAINING_COHORT_DIR = tmp_path / "cohort"
    monkeypatch.setattr(seeding, "load_nhanes", nhanes_rows)
    path = lab_records_file(tmp_path, deficient=20, sound=100)
    main(["hospital"])
    for _ in range(2):
        main(["lab-records", "--csv", str(path), "--provide"])
    provided = TrainingCohort.objects.provided()
    assert provided is not None
    assert (provided.past_patients, provided.iron_deficient) == (120, 20)
    assert provided.provided_by.username == "director"
