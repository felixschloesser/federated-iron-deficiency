"""The demo's preparation helpers (spec §9); compose.yaml is in tests/test_compose.py."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


STATUSES = {
    "uz-leuven": "2 screening models, none deployed",
    "heilig-hart-leuven": "no screening model yet",
    "az-diest": "Screening model of 29 Oct 2026, 20:55 deployed (1 in all)",
}


def test_the_summary_names_each_party_with_its_address_and_state() -> None:
    from tools.demo import summary

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
    from tools.demo import summary

    assert "Next: train with `docker compose run --rm train`" in summary(STATUSES)
    trained = {**STATUSES, "heilig-hart-leuven": "1 screening model, none deployed"}
    assert "Next: deploy a screening model as director-1" in summary(trained)
    deployed = dict.fromkeys(STATUSES, "Screening model of … deployed (1 in all)")
    assert "Next:" not in summary(deployed)


def test_each_practice_and_its_hospital_seed_the_same_number_of_patients() -> None:
    from tools.demo import PATIENTS, seed_arguments

    assert [PATIENTS[cycle] for cycle in PATIENTS] == [40, 24, 12]
    for partition, cycle in enumerate(PATIENTS):
        arguments = seed_arguments(partition, Path("nhanes.csv"))
        assert arguments[arguments.index("--patients") + 1] == str(PATIENTS[cycle])


def test_the_summary_names_the_http_port_when_it_is_not_80() -> None:
    from tools.demo import summary

    text = summary(STATUSES, http_port=8080)
    assert "http://uz-leuven.localhost:8080/" in text


def test_demo_toml_describes_exactly_the_hospitals_training_knows() -> None:
    import tomllib

    from iron_deficiency.dataset import HOSPITALS, hospital_slug

    parties = tomllib.loads((ROOT / "demo.toml").read_text())
    assert set(parties["hospitals"]) == {hospital_slug(n) for n in HOSPITALS.values()}


def test_each_hospitals_practice_colours_and_patients_come_from_demo_toml() -> None:
    import tomllib

    from iron_deficiency.dataset import HOSPITALS, hospital_slug
    from tools.demo import COLOURS, PATIENTS, PRACTICES

    hospitals = tomllib.loads((ROOT / "demo.toml").read_text())["hospitals"]
    for cycle, name in HOSPITALS.items():
        entry = hospitals[hospital_slug(name)]
        assert PRACTICES[cycle] == entry["practice"]
        assert COLOURS[cycle] == (entry["colour"], entry["practice_colour"])
        assert PATIENTS[cycle] == entry["patients"]
