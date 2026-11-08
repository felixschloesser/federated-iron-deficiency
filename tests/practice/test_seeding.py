"""The practice's demo data (python -m demo.seed practice): its general practitioner, its
stock of sample IDs, and a patient, with a made-up name, for each participant of
the stock marked a patient."""

from pathlib import Path

import pytest
from pytest_django.fixtures import Settings

from demo.seed import main
from demo.seeding import names
from demo.seeding import participants as seeding
from tests.conftest import PEOPLE, nhanes_rows
from web.practice.models import Patient, SampleId
from web.shared.accounts.models import User
from web.shared.accounts.roles import Role, role_of
from web.shared.vocabulary import RegisteredSex

pytestmark = pytest.mark.django_db


@pytest.fixture
def development(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    settings.DEBUG = True
    monkeypatch.setattr(seeding, "load_nhanes", nhanes_rows)


@pytest.fixture
def seeded(development: None) -> None:
    main(["practice"])


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


def test_seeds_three_sample_ids_for_each_patient_holding_its_participant(
    seeded: None,
) -> None:
    """The stock holds each patient's own participant, so a patient's first sample
    usually carries that participant's blood (demo/seeding/participants.py)."""
    rows = nhanes_rows().set_index("sample_id")
    assert SampleId.objects.count() == 3 * Patient.objects.count()
    for sample_id in SampleId.objects.all():
        row = rows.loc[int(sample_id.value)]
        assert sample_id.registered_sex == str(row["sex"]).lower()
        assert sample_id.age == row["age"]
    patients = seeding.choose(nhanes_rows(), seed=0)
    stocked = set(SampleId.objects.values_list("value", flat=True))
    assert {str(seqn) for seqn in patients["sample_id"]} <= stocked


def test_running_twice_changes_nothing(seeded: None) -> None:
    main(["practice"])
    assert User.objects.count() == 2
    assert Patient.objects.count() == 3 * len(PEOPLE)


def test_refuses_outside_development(settings: Settings) -> None:
    settings.DEBUG = False
    with pytest.raises(SystemExit, match="DJANGO_DEBUG=1"):
        main(["practice"])
    assert not User.objects.exists()


def test_each_seed_chooses_other_participants(development: None) -> None:
    rows = nhanes_rows()
    assert not seeding.choose(rows, seed=0).equals(seeding.choose(rows, seed=1))
    main(["practice", "--seed", "1"])
    assert Patient.objects.count() == 3 * len(PEOPLE)


def test_reads_participants_from_a_csv(settings: Settings, tmp_path: Path) -> None:
    settings.DEBUG = True
    csv = tmp_path / "nhanes.csv"
    nhanes_rows().to_csv(csv, index=False)
    main(["practice", "--nhanes", str(csv)])
    assert Patient.objects.count() == 3 * len(PEOPLE)


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


def test_the_number_of_patients_is_a_parameter(development: None) -> None:
    main(["practice", "--patients", "6"])
    assert Patient.objects.count() == 6
    # Shared by the groups, the first ones rounding up: 2, 2, 1, 1.
    assert Patient.objects.filter(age=30).count() == 2
    assert Patient.objects.filter(age=70).count() == 1


def test_seeds_from_nhanes_downloads_extract(
    settings: Settings, tmp_path: Path
) -> None:
    """nhanes-download's extract, as NHANES writes ages: 30.0, not 30
    (demo/nhanes.py)."""
    settings.DEBUG = True
    rows = nhanes_rows().astype({"age": float})
    extract = tmp_path / "sample-ids.csv"
    seeding.stock(rows, seed=0)[["sample_id", "sex", "age", "patient"]].to_csv(
        extract, index=False
    )
    main(["practice", "--rows", str(extract)])
    assert Patient.objects.count() == 3 * len(PEOPLE)
    assert set(Patient.objects.values_list("age", flat=True)) <= {30, 25, 35, 70}
