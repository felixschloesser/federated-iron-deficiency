"""The hospital's demo data (seed_hospital): its staff, and what its analyser
stand-in measures for each NHANES participant it was given."""

from pathlib import Path

import pytest
from django.core.management import CommandError, call_command
from pytest_django.fixtures import Settings

from ml.cohort import CBC_VARS
from tests.conftest import PEOPLE, nhanes_rows
from web.accounts.models import User
from web.accounts.roles import Role, role_of
from web.hospital.nhanes.models import MADE_UP_FERRITIN, Participant
from web.seeding import command as seeding
from web.vocabulary import RESULT_NAMES
from web.vocabulary import Test as OrderedTest

pytestmark = pytest.mark.django_db


@pytest.fixture
def development(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    settings.DEBUG = True
    monkeypatch.setattr(seeding, "load_nhanes", nhanes_rows)


@pytest.fixture
def seeded(development: None) -> None:
    call_command("seed_hospital")


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
    call_command("seed_hospital")
    assert User.objects.count() == 3
    assert Participant.objects.count() == 3 * len(PEOPLE)


def test_refuses_outside_development(settings: Settings) -> None:
    settings.DEBUG = False
    with pytest.raises(CommandError, match="DJANGO_DEBUG=1"):
        call_command("seed_hospital")
    assert not User.objects.exists()


def test_reads_participants_from_a_csv(settings: Settings, tmp_path: Path) -> None:
    settings.DEBUG = True
    csv = tmp_path / "nhanes.csv"
    nhanes_rows().to_csv(csv, index=False)
    call_command("seed_hospital", "--nhanes", str(csv))
    assert Participant.objects.count() == 3 * len(PEOPLE)


def test_eligible_women_without_ferritin_are_never_seeded(seeded: None) -> None:
    assert not Participant.objects.filter(seqn__range=(1040, 1049)).exists()


def test_the_number_of_participants_is_a_parameter(development: None) -> None:
    call_command("seed_hospital", "--patients", "6")
    assert Participant.objects.count() == 6


def test_a_made_up_ferritin_is_reported_under_its_own_name() -> None:
    participant = Participant(seqn=1, cbc={}, ferritin=None, made_up_ferritin=60.0)
    assert participant.measure(OrderedTest.FERRITIN) == {MADE_UP_FERRITIN: 60.0}
    assert RESULT_NAMES[MADE_UP_FERRITIN].name == "Ferritin (made up for the demo)"
    assert RESULT_NAMES[MADE_UP_FERRITIN].unit == "ng/mL"
