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
    ("Female", 40, None),  # eligible, no ferritin
    ("Male", 35, None),  # men
    ("Female", 70, None),  # women outside 18-49
]


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
        for group, (sex, age, ferritin) in enumerate(PEOPLE)
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
            assert participant.cbc == dict.fromkeys(CBC_VARS, float(group))
            patient = Patient.objects.get(nhanes_number=str(participant.seqn))
            assert patient.registered_sex == sex.lower()
            assert patient.age == age


def test_patients_are_shared_between_the_general_practitioners(seeded: None) -> None:
    counts = [
        practitioner.patients.count()
        for practitioner in GeneralPractitioner.objects.all()
    ]
    assert sorted(counts) == [7, 8]
    assert Patient.objects.filter(name="Test Patient 1").exists()


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
