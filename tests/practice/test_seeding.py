"""The practice's demo data (python -m demo.seed practice): its general
practitioner, its stock of sample IDs, and its patients, with made-up names."""

from pathlib import Path

import pytest
from pytest_django.fixtures import Settings

from demo.seed import main
from demo.seeding import names
from demo.seeding import participants as seeding
from tests.conftest import PEOPLE, nhanes_rows, write_extracts
from web.practice.models import Patient, SampleId
from web.shared.accounts.models import User
from web.shared.accounts.roles import Role, role_of
from web.shared.vocabulary import RegisteredSex

pytestmark = pytest.mark.django_db


@pytest.fixture
def extract(settings: Settings, tmp_path: Path) -> list[str]:
    """demo.seed's arguments for the practice, from nhanes-download's extract,
    in development."""
    settings.DEBUG = True
    _, practice = write_extracts(tmp_path)
    return [
        "practice",
        "--sample-ids",
        str(practice / "sample-ids.csv"),
        "--patients",
        str(practice / "patients.csv"),
    ]


@pytest.fixture
def seeded(extract: list[str]) -> None:
    main(extract)


def test_seeds_its_one_general_practitioner(seeded: None) -> None:
    assert {role_of(user) for user in User.objects.all()} == {
        Role.GENERAL_PRACTITIONER,
        None,  # no-role: for the refusal at login
    }
    assert User.objects.get(role=Role.GENERAL_PRACTITIONER).username == "doctor"


def test_seeds_three_patients_of_each_group_from_nhanes(seeded: None) -> None:
    rows = nhanes_rows()
    assert Patient.objects.count() == 3 * len(PEOPLE)
    seeded_people = {(row["sex"].lower(), row["age"]) for _, row in rows.iterrows()}
    for patient in Patient.objects.all():
        assert (patient.registered_sex, patient.age) in seeded_people


def test_seeds_three_sample_ids_for_each_patient_from_the_hospitals_pool(
    seeded: None,
) -> None:
    """Every sample ID names a participant the hospitals' analyser holds
    (demo/seeding/participants.py)."""
    pool = {str(seqn) for seqn in seeding.pool(nhanes_rows())["sample_id"]}
    stocked = list(SampleId.objects.values_list("value", flat=True))
    assert len(stocked) == 3 * Patient.objects.count()
    assert set(stocked) <= pool


def test_running_twice_changes_nothing(seeded: None, extract: list[str]) -> None:
    main(extract)
    assert User.objects.count() == 2
    assert Patient.objects.count() == 3 * len(PEOPLE)


def test_refuses_outside_development(settings: Settings, extract: list[str]) -> None:
    settings.DEBUG = False
    with pytest.raises(SystemExit, match="DJANGO_DEBUG=1"):
        main(extract)
    assert not User.objects.exists()


def test_eligible_women_without_ferritin_are_never_seeded(seeded: None) -> None:
    assert not Patient.objects.filter(age=40).exists()


def test_patients_get_fictional_flemish_names_matching_their_sex(seeded: None) -> None:
    for patient in Patient.objects.all():
        first, last = patient.name.split(" ", 1)
        sex = RegisteredSex(patient.registered_sex)
        assert first in names.first_names(sex), patient.name
        assert last in names.SURNAMES, patient.name
    assert Patient.objects.values("name").distinct().count() > 1


def test_a_patients_name_is_the_same_on_every_seed() -> None:
    female = RegisteredSex.FEMALE
    assert names.patient_name(135318, female) == names.patient_name(135318, female)
    assert names.patient_name(135318, female) != names.patient_name(135319, female)


def test_seeds_from_nhanes_downloads_extract(
    settings: Settings, tmp_path: Path
) -> None:
    """nhanes-download's extract, as NHANES writes ages: 30.0, not 30
    (demo/nhanes.py)."""
    settings.DEBUG = True
    rows = nhanes_rows().astype({"age": float})
    seeding.stock(rows, seed=0).to_csv(tmp_path / "sample-ids.csv", index=False)
    seeding.patients(rows, seed=0).to_csv(tmp_path / "patients.csv", index=False)
    main(
        [
            "practice",
            "--sample-ids",
            str(tmp_path / "sample-ids.csv"),
            "--patients",
            str(tmp_path / "patients.csv"),
        ]
    )
    assert Patient.objects.count() == 3 * len(PEOPLE)
    assert set(Patient.objects.values_list("age", flat=True)) <= {30, 25, 35, 70}
