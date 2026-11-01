"""The demo data commands used for manual and browser checks: seed_hospital
and seed_practice, both run in a development checkout."""

from pathlib import Path

import pandas as pd
import pytest
from django.core.management import CommandError, call_command
from pytest_django.fixtures import Settings

from iron_deficiency.dataset import CBC_VARS
from web.accounts import demo
from web.accounts.models import User
from web.accounts.roles import Role, role_of
from web.nhanes.models import Participant
from web.practice.models import GeneralPractitioner, Patient

pytestmark = pytest.mark.django_db

# (sex, age, ferritin) per group, in the order demo.Group lists them.
PEOPLE = [
    ("Female", 30, 8.0),  # eligible, ferritin below 15
    ("Female", 25, 40.0),  # eligible, ferritin 15 or more
    ("Male", 35, None),  # men
    ("Female", 70, None),  # women outside 18-49
]
# Eligible women whom NHANES did not measure: never seeded.
UNMEASURED = ("Female", 40, None)


def nhanes_rows() -> pd.DataFrame:
    """Four participants per group, so the seed has to choose."""
    rows = [
        {
            "sample_id": 1000 + 10 * group + copy,
            "sex": sex,
            "age": age,
            **dict.fromkeys(CBC_VARS, float(group)),
            "LBXFER": ferritin,
        }
        for group, (sex, age, ferritin) in enumerate([*PEOPLE, UNMEASURED])
        for copy in range(4)
    ]
    return pd.DataFrame(rows)


def seed(*args: str) -> None:
    call_command("seed_hospital", *args)
    call_command("seed_practice", *args)


@pytest.fixture
def seeded(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    settings.DEBUG = True
    monkeypatch.setattr(demo, "load_nhanes", nhanes_rows)
    seed()


def test_seeds_accounts_of_every_role(seeded: None) -> None:
    roles = {role_of(user) for user in User.objects.all()}
    assert roles == {*Role, None}  # no-role: for the refusal at login
    assert User.objects.get(username="lab-1").check_password("demo-pass-2026")


def test_seeds_three_patients_of_each_group_from_nhanes(seeded: None) -> None:
    assert Patient.objects.count() == 3 * len(PEOPLE)
    for group, (sex, age, ferritin) in enumerate(PEOPLE):
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
            patient = Patient.objects.get(nhanes_number=str(participant.seqn))
            assert patient.registered_sex == sex.lower()
            assert patient.age == age


def test_patients_are_shared_between_the_general_practitioners(seeded: None) -> None:
    counts = [
        practitioner.patients.count()
        for practitioner in GeneralPractitioner.objects.all()
    ]
    assert sorted(counts) == [6, 6]


def test_running_twice_changes_nothing(seeded: None) -> None:
    seed()
    assert User.objects.count() == 5
    assert Patient.objects.count() == 3 * len(PEOPLE)


def test_refuses_outside_development(settings: Settings) -> None:
    settings.DEBUG = False
    with pytest.raises(CommandError, match="DJANGO_DEBUG=1"):
        seed()
    assert not User.objects.exists()


def test_each_hospital_seeds_other_participants(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings.DEBUG = True
    monkeypatch.setattr(demo, "load_nhanes", nhanes_rows)
    rows = nhanes_rows()
    assert not demo.choose(rows, seed=0).equals(demo.choose(rows, seed=1))
    seed("--seed", "1")
    assert Patient.objects.count() == 3 * len(PEOPLE)


def test_reads_participants_from_a_csv(settings: Settings, tmp_path: Path) -> None:
    settings.DEBUG = True
    csv = tmp_path / "nhanes.csv"
    nhanes_rows().to_csv(csv, index=False)
    seed("--nhanes", str(csv))
    assert Patient.objects.count() == 3 * len(PEOPLE)


def test_a_hospital_seeds_no_patients(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings.DEBUG = True
    monkeypatch.setattr(demo, "load_nhanes", nhanes_rows)
    call_command("seed_hospital")
    assert not Patient.objects.exists()
    assert Participant.objects.count() == 3 * len(PEOPLE)
    assert {role_of(user) for user in User.objects.all()} == {
        Role.LABORATORY_STAFF,
        Role.LABORATORY_DIRECTOR,
        None,
    }


def test_a_practice_seeds_no_analyser_values(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings.DEBUG = True
    monkeypatch.setattr(demo, "load_nhanes", nhanes_rows)
    call_command("seed_practice")
    assert not Participant.objects.exists()
    assert Patient.objects.count() == 3 * len(PEOPLE)
    assert {role_of(user) for user in User.objects.all()} == {
        Role.GENERAL_PRACTITIONER,
        None,
    }


def test_eligible_women_without_ferritin_are_never_seeded(seeded: None) -> None:
    assert not Participant.objects.filter(seqn__range=(1040, 1049)).exists()
    assert not Patient.objects.filter(age=40).exists()


def test_a_made_up_ferritin_is_reported_under_its_own_name() -> None:
    from web.nhanes.models import MADE_UP_FERRITIN
    from web.vocabulary import RESULT_NAMES, Test

    participant = Participant(seqn=1, cbc={}, ferritin=None, made_up_ferritin=60.0)
    assert participant.measure(Test.FERRITIN) == {MADE_UP_FERRITIN: 60.0}
    assert RESULT_NAMES[MADE_UP_FERRITIN].name == "Ferritin (made up for the demo)"
    assert RESULT_NAMES[MADE_UP_FERRITIN].unit == "ng/mL"


def test_patients_get_fictional_flemish_names_matching_their_sex(seeded: None) -> None:
    for patient in Patient.objects.all():
        first, last = patient.name.split(" ", 1)
        assert first in demo.FIRST_NAMES[patient.registered_sex], patient.name
        assert last in demo.SURNAMES, patient.name
    assert Patient.objects.values("name").distinct().count() > 1


def test_a_patients_name_is_the_same_on_every_seed() -> None:
    assert demo.patient_name(135318, "female") == demo.patient_name(135318, "female")
    assert demo.patient_name(135318, "female") != demo.patient_name(135319, "female")
