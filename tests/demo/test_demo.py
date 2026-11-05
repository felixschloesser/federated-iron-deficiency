"""The demo's preparation helpers (spec §9); compose.yaml is in tests/demo/test_compose.py."""

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
    assert "laboratory staff: lab-1 · laboratory director: director-1" in text
    assert "general practitioner: doctor" in text
    for line in (
        "UZ Leuven  ",
        "http://uz-leuven.localhost/   2 screening models, none deployed",
        "http://heilig-hart-leuven.localhost/   no screening model yet",
        "Huisartsenpraktijk De Akker  ",
        "http://huisartsenpraktijk-de-ceder.localhost/",
        "Ctrl-C stops every party.",
    ):
        assert line in text, line
    # A practice sends samples to every hospital's laboratory, not to one (R22).
    assert "→" not in text
    assert "Accounts" not in text


def test_the_next_step_follows_the_hospitals_state() -> None:
    from demo.demo import summary

    assert "Next: train with `docker compose run --rm train`" in summary(STATUSES)
    trained = {**STATUSES, "heilig-hart-leuven": "1 screening model, none deployed"}
    assert "Next: deploy a screening model as director-1" in summary(trained)
    deployed = dict.fromkeys(STATUSES, "Screening model of … deployed (1 in all)")
    assert "Next:" not in summary(deployed)


def test_each_practice_and_its_hospital_seed_the_same_number_of_patients() -> None:
    from demo.demo import PATIENTS, seed_arguments

    assert [PATIENTS[cycle] for cycle in PATIENTS] == [40, 24, 12]
    for partition, cycle in enumerate(PATIENTS):
        arguments = seed_arguments(partition, Path("nhanes.csv"))
        assert arguments[arguments.index("--patients") + 1] == str(PATIENTS[cycle])


def test_the_summary_names_the_http_port_when_it_is_not_80() -> None:
    from demo.demo import summary

    text = summary(STATUSES, http_port=8080)
    assert "http://uz-leuven.localhost:8080/" in text


def test_demo_toml_describes_exactly_the_hospitals_training_knows() -> None:
    import tomllib

    from iron_deficiency.dataset import HOSPITALS, hospital_slug

    parties = tomllib.loads((ROOT / "demo" / "demo.toml").read_text())
    assert set(parties["hospitals"]) == {hospital_slug(n) for n in HOSPITALS.values()}


def test_each_hospitals_practice_colours_and_patients_come_from_demo_toml() -> None:
    import tomllib

    from demo.demo import COLOURS, PATIENTS, PRACTICES
    from iron_deficiency.dataset import HOSPITALS, hospital_slug

    hospitals = tomllib.loads((ROOT / "demo" / "demo.toml").read_text())["hospitals"]
    for cycle, name in HOSPITALS.items():
        entry = hospitals[hospital_slug(name)]
        assert PRACTICES[cycle] == entry["practice"]
        assert COLOURS[cycle] == (entry["colour"], entry["practice_colour"])
        assert PATIENTS[cycle] == entry["patients"]


# What each party's folder may hold: the report's DFD stores, and the Django
# secret key its web app uses (spec §9). Nothing from the NHANES cycle
# that stands in for new samples: the seed commands get their participants
# from prepare alone.
PARTY_FOLDERS = {
    "startup": {
        "superlink",  # DS3
        "final-models",  # DS4
        "flwr-home",
    },
    "hospitals": {
        "cohort",  # DS2
        "final-models",  # DS5
        "web.sqlite3",  # DS6, DS8
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

    import iron_deficiency.dataset
    from demo.demo import hospitals, nhanes_csv, practices, prepare
    from iron_deficiency.dataset import CBC_VARS

    class Cohort:
        def save_to_disk(self, path: Path) -> None:
            path.mkdir(parents=True)

    class Cohorts:
        def load_partition(self, partition: int) -> Cohort:
            return Cohort()

    samples = pd.DataFrame(
        {"sample_id": [1], "sex": ["Female"], "age": [30]}
        | {var: [1.0] for var in CBC_VARS}
    )
    ferritin = pd.DataFrame({"sample_id": [1], "LBXFER": [20.0]})
    monkeypatch.setattr(iron_deficiency.dataset, "load_federated_dataset", Cohorts)
    monkeypatch.setattr(iron_deficiency.dataset, "load_new_samples", lambda: samples)
    monkeypatch.setattr(iron_deficiency.dataset, "load_ferritin", lambda: ferritin)
    # A folder prepared before the participants stayed with prepare.
    stale = [tmp_path / "hospitals" / hospitals()[0][1]]
    stale += [tmp_path / "practices" / practices()[0][1]]
    for folder in stale:
        folder.mkdir(parents=True)
        (folder / "nhanes.csv").write_text("sample_id\n1\n")

    prepare(tmp_path)

    folders = [(tmp_path / "startup", "startup")]
    folders += [(tmp_path / "hospitals" / slug, "hospitals") for _, slug in hospitals()]
    folders += [(tmp_path / "practices" / slug, "practices") for _, slug in practices()]
    for folder, kind in folders:
        held = {entry.name for entry in folder.iterdir()}
        assert held <= PARTY_FOLDERS[kind], (folder.name, held - PARTY_FOLDERS[kind])
    # The seed commands still get the cycle, from where only prepare looks.
    assert nhanes_csv(tmp_path).is_file()
