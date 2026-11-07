"""The demo's preparation helpers (demo/README.md); compose.yaml is in tests/quality/security/test_compose.py."""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


STATUSES = {
    "uz-leuven": "2 screening models, none deployed",
    "heilig-hart-leuven": "no screening model yet",
    "az-diest": "Screening model of 29 Oct 2026, 20:55 deployed (1 in all)",
}


def test_the_summary_names_each_party_with_its_address_and_state() -> None:
    from demo.demo import summary

    text = summary(STATUSES)
    assert "Password for every account: demo-pass-2026" in text
    assert "laboratory staff: staff · laboratory director: director" in text
    assert "general practitioner: doctor" in text
    assert "data scientist: data-scientist" in text
    for line in (
        "UZ Leuven  ",
        "http://uz-leuven.localhost/   2 screening models, none deployed",
        "http://heilig-hart-leuven.localhost/   no screening model yet",
        "  http://startup.localhost/",
        "Huisartsenpraktijk De Akker  ",
        "http://huisartsenpraktijk-de-ceder.localhost/",
        "Ctrl-C stops every party.",
    ):
        assert line in text, line
    # A practice sends samples to every hospital's laboratory, not to one (features/practice/ordering.feature).
    assert "→" not in text
    assert "Accounts" not in text


def test_the_next_step_follows_the_hospitals_state() -> None:
    from demo.demo import summary

    assert "Next: submit a training run as data-scientist" in summary(STATUSES)
    assert "`docker compose run --rm train`" in summary(STATUSES)
    trained = {**STATUSES, "heilig-hart-leuven": "1 screening model, none deployed"}
    assert "Next: deploy a screening model as director" in summary(trained)
    deployed = dict.fromkeys(STATUSES, "Screening model of … deployed (1 in all)")
    assert "Next:" not in summary(deployed)


def test_each_practice_and_its_hospital_seed_the_same_number_of_patients() -> None:
    from demo.demo import seed_arguments
    from demo.topology import PATIENTS

    assert [PATIENTS[cycle] for cycle in PATIENTS] == [40, 24, 12]
    for partition, cycle in enumerate(PATIENTS):
        arguments = seed_arguments(partition, Path("nhanes.csv"))
        assert arguments[arguments.index("--patients") + 1] == str(PATIENTS[cycle])


def test_every_hospital_has_a_tube_for_every_practices_patients() -> None:
    """Any practice may send a sample to any hospital (features/practice/ordering.feature), so every hospital's
    analyser stand-in seeds every practice's participants."""
    from demo.demo import seed_arguments, tube_seeds
    from demo.topology import PATIENTS

    nhanes = Path("nhanes.csv")
    assert tube_seeds(nhanes) == [
        seed_arguments(partition, nhanes) for partition in range(len(PATIENTS))
    ]


def test_every_hospital_knows_every_practice_by_its_folder_name() -> None:
    """Any practice may send a sample to any hospital (features/practice/ordering.feature),
    so each hospital registers every practice, by the certificate name its app
    sends: its folder name, as compose.yaml sets it."""
    from demo.demo import practice_arguments
    from demo.topology import PRACTICES
    from ml.dataset import CYCLES, hospital_slug

    assert practice_arguments() == [
        [hospital_slug(PRACTICES[cycle]), PRACTICES[cycle]] for cycle in CYCLES
    ]


def test_the_startup_knows_every_hospital_by_the_name_its_web_app_sends() -> None:
    """Any hospital may fetch released final models (features/startup/release.feature),
    so the startup registers every one, by the certificate name its web app sends:
    its folder name, as compose.yaml sets it."""
    from demo.demo import hospital_arguments
    from ml.dataset import CYCLES, HOSPITALS, hospital_slug

    assert hospital_arguments() == [
        [hospital_slug(HOSPITALS[cycle]), HOSPITALS[cycle]] for cycle in CYCLES
    ]


def test_each_practice_sends_to_its_own_hospital_unless_told_otherwise() -> None:
    """Every hospital's laboratory, its paired hospital's the primary one, so
    lab orders follow the hospitals' sizes by default."""
    from demo.demo import laboratory_arguments, messaging_host
    from ml.dataset import CYCLES, HOSPITALS, hospital_slug

    for cycle in CYCLES:
        arguments = laboratory_arguments(cycle)
        assert [argument[0] for argument in arguments] == [
            HOSPITALS[other] for other in CYCLES
        ]
        for argument, other in zip(arguments, CYCLES, strict=True):
            host = messaging_host(hospital_slug(HOSPITALS[other]))
            assert argument[1] == f"{host}:8441"
            assert ("--primary" in argument) is (other == cycle)


def test_the_summary_names_the_http_port_when_it_is_not_80() -> None:
    from demo.demo import summary

    text = summary(STATUSES, http_port=8080)
    assert "http://uz-leuven.localhost:8080/" in text


# What each party's folder may hold: the report's DFD stores, and the Django
# secret key its web app uses (demo/README.md). Nothing from the NHANES cycle
# that stands in for new samples: the seed commands get their participants
# from prepare alone.
PARTY_FOLDERS = {
    "startup": {
        "superlink",  # the SuperLink's own state, no DFD store
        "final-models",  # DS4
        "flwr-home",
        "web.sqlite3",  # the data scientist's account
        ".secret_key",
    },
    "hospitals": {
        "cohort",  # DS2
        "screening-models",  # DS5
        "web.sqlite3",  # DS1, DS6, DS8, DS9
        ".secret_key",
    },
    "practices": {
        "web.sqlite3",  # DS7
        ".secret_key",
    },
}


def test_each_partys_folder_holds_only_its_dfd_stores_and_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import pandas as pd

    import ml.dataset
    from demo.demo import hospitals, lab_records_csv, nhanes_csv, practices, prepare
    from ml.cohort import CBC_VARS

    samples = pd.DataFrame(
        {"sample_id": [1], "sex": ["Female"], "age": [30]}
        | {var: [1.0] for var in CBC_VARS}
    )
    ferritin = pd.DataFrame({"sample_id": [1], "LBXFER": [20.0]})
    records = pd.DataFrame(
        {"sex": ["Female"], "age": [30], "LBXFER": [20.0]}
        | {var: [1.0] for var in CBC_VARS}
    )
    monkeypatch.setattr(ml.dataset, "load_lab_records", lambda cycle: records)
    monkeypatch.setattr(ml.dataset, "load_new_samples", lambda: samples)
    monkeypatch.setattr(ml.dataset, "load_ferritin", lambda: ferritin)
    # A folder prepared before the participants stayed with prepare.
    stale = [tmp_path / "hospitals" / hospitals()[0][1]]
    stale += [tmp_path / "practices" / practices()[0][1]]
    for folder in stale:
        folder.mkdir(parents=True)
        (folder / "nhanes.csv").write_text("sample_id\n1\n")
    # A hospital prepared before its final models moved to screening-models.
    (stale[0] / "final-models").mkdir()
    (stale[0] / "final-models" / "7.pt").write_text("model")

    prepare(tmp_path)

    folders = [(tmp_path / "startup", "startup")]
    folders += [(tmp_path / "hospitals" / slug, "hospitals") for _, slug in hospitals()]
    folders += [(tmp_path / "practices" / slug, "practices") for _, slug in practices()]
    for folder, kind in folders:
        held = {entry.name for entry in folder.iterdir()}
        assert held <= PARTY_FOLDERS[kind], (folder.name, held - PARTY_FOLDERS[kind])
    # The seed commands still get the cycle, from where only prepare looks.
    assert nhanes_csv(tmp_path).is_file()
    assert (stale[0] / "screening-models" / "7.pt").read_text() == "model"
    # Each hospital's lab records (DS1) for its seed command, beside the
    # downloads; its cohort folder empty until its laboratory director provides
    # one (features/hospital/training_cohort.feature).
    for _, slug in hospitals():
        assert lab_records_csv(tmp_path, slug).is_file()
        assert list((tmp_path / "hospitals" / slug / "cohort").iterdir()) == []


def test_two_hospitals_provide_their_training_cohort_at_start(tmp_path: Path) -> None:
    """AZ Diest's laboratory director has not, so a training run shows a hospital
    taking no part until its director provides one."""
    from demo.demo import lab_record_arguments

    provides = {
        slug: "--provide" in arguments
        for slug, arguments in lab_record_arguments(tmp_path).items()
    }
    assert provides == {
        "uz-leuven": True,
        "heilig-hart-leuven": True,
        "az-diest": False,
    }
