"""The demo launcher: one folder and one process per party (spec §9, R21)."""

from pathlib import Path

from iron_deficiency.dataset import HOSPITALS, hospital_slug
from tools.demo import PRACTICES, plan

DEMO = Path("/demo")
HOSPITAL_SLUGS = {hospital_slug(name) for name in HOSPITALS.values()}
PRACTICE_SLUGS = {hospital_slug(name) for name in PRACTICES.values()}


def names(kind: str) -> list[str]:
    return sorted(
        process.name for process in plan(DEMO) if process.name.startswith(kind)
    )


def test_one_process_of_each_kind_per_party() -> None:
    assert names("superlink") == ["superlink"]
    assert names("supernode") == sorted(f"supernode {s}" for s in HOSPITAL_SLUGS)
    assert names("messaging") == sorted(f"messaging {s}" for s in HOSPITAL_SLUGS)
    assert names("web") == sorted(
        f"web {slug}" for slug in HOSPITAL_SLUGS | PRACTICE_SLUGS
    )
    assert names("reports") == sorted(f"reports {s}" for s in PRACTICE_SLUGS)


def test_each_process_sees_only_its_own_folder() -> None:
    folders = {
        DEMO / "startup",
        *(DEMO / "hospitals" / slug for slug in HOSPITAL_SLUGS),
        *(DEMO / "practices" / slug for slug in PRACTICE_SLUGS),
    }
    for process in plan(DEMO):
        text = " ".join([*process.command, *process.env.values()])
        # A SuperNode trusts the startup's CA through its own copy of its certificate.
        assert str(process.folder) in text, process.name
        for other in folders - {process.folder}:
            assert str(other) not in text, process.name


def test_the_superlink_keeps_its_state_with_the_startup() -> None:
    (superlink,) = [process for process in plan(DEMO) if process.name == "superlink"]
    assert superlink.folder == DEMO / "startup"
    assert str(DEMO / "startup" / "superlink") in " ".join(superlink.command)


def test_every_flower_connection_uses_tls() -> None:
    for process in plan(DEMO):
        assert "--insecure" not in process.command, process.name


def test_every_process_listens_on_its_own_port() -> None:
    addresses = sorted(
        process.command[-1]
        for process in plan(DEMO)
        if process.name.split()[0] in {"web", "messaging"}
    )
    assert addresses == [
        f"127.0.0.1:{port}"
        for port in (8001, 8002, 8003, 8011, 8012, 8013, 8441, 8442, 8443)
    ]


def test_each_web_app_knows_its_party_name() -> None:
    hospital_names = {
        process.name: process.env["HOSPITAL_NAME"]
        for process in plan(DEMO)
        if "HOSPITAL_NAME" in process.env
    }
    assert hospital_names == {
        f"web {hospital_slug(name)}": name for name in HOSPITALS.values()
    }
    practice_names = {
        process.name: process.env["PRACTICE_NAME"]
        for process in plan(DEMO)
        if "PRACTICE_NAME" in process.env
    }
    assert practice_names == {
        f"web {hospital_slug(name)}": name for name in PRACTICES.values()
    }


def test_each_practice_talks_to_its_own_hospital() -> None:
    endpoints = {
        process.name.split()[1]: process.command[-1]
        for process in plan(DEMO)
        if process.name.startswith("messaging")
    }
    for cycle, practice in PRACTICES.items():
        address = endpoints[hospital_slug(HOSPITALS[cycle])]
        for process in plan(DEMO):
            if process.name.endswith(f" {hospital_slug(practice)}"):
                assert process.env["MESSAGING_ADDRESS"] == address, process.name


def test_each_web_app_has_its_own_colour_in_its_hospitals_family() -> None:
    from tools.demo import COLOURS

    colours = {
        process.name: process.env["PARTY_COLOUR"]
        for process in plan(DEMO)
        if process.name.startswith("web ")
    }
    assert len(set(colours.values())) == len(colours) == 6
    for cycle, (hospital, practice) in COLOURS.items():
        assert colours[f"web {hospital_slug(HOSPITALS[cycle])}"] == hospital
        assert colours[f"web {hospital_slug(PRACTICES[cycle])}"] == practice
    vendor = Path(__file__).resolve().parents[1] / "static/css/vendor/pico-2.1.1"
    for colour in colours.values():
        assert (vendor / f"pico.{colour}.min.css").is_file(), colour


def test_reset_removes_only_the_web_databases(tmp_path: Path) -> None:
    from tools.demo import hospital_dir, practice_dir, reset

    kept = []
    removed = []
    for folder in (hospital_dir(tmp_path, "uz-leuven"), practice_dir(tmp_path, "a")):
        (folder / "certificates").mkdir(parents=True)
        for name in ("nhanes.csv", "certificates/ca.crt"):
            (folder / name).write_text("keep")
            kept.append(folder / name)
        (folder / "web.sqlite3").write_text("old")
        removed.append(folder / "web.sqlite3")
    reset(tmp_path, demo_running=lambda: False)
    assert all(path.exists() for path in kept)
    assert not any(path.exists() for path in removed)


def test_reset_refuses_while_the_demo_runs(tmp_path: Path) -> None:
    import pytest

    from tools.demo import hospital_dir, reset

    database = hospital_dir(tmp_path, "uz-leuven") / "web.sqlite3"
    database.parent.mkdir(parents=True)
    database.write_text("in use")
    with pytest.raises(SystemExit, match="Stop the demo"):
        reset(tmp_path, demo_running=lambda: True)
    assert database.exists()


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
    assert "general practitioners: doctor-a, doctor-b" in text
    for line in (
        "UZ Leuven  ",
        "http://127.0.0.1:8001/   2 screening models, none deployed",
        "http://127.0.0.1:8002/   no screening model yet",
        "Huisartsenpraktijk De Akker → UZ Leuven",
        "http://127.0.0.1:8013/",
        "Ctrl-C stops every party.",
    ):
        assert line in text, line
    assert "Accounts" not in text


def test_the_next_step_follows_the_hospitals_state() -> None:
    from tools.demo import summary

    assert "Next: train with `docker compose run --rm train`" in summary(STATUSES)
    trained = {**STATUSES, "heilig-hart-leuven": "1 screening model, none deployed"}
    assert "Next: deploy a screening model as director-1" in summary(trained)
    deployed = dict.fromkeys(STATUSES, "Screening model of … deployed (1 in all)")
    assert "Next:" not in summary(deployed)


def test_each_practice_checks_for_lab_reports_every_five_seconds() -> None:
    # The demo squeezes hours into seconds; a real practice checks every 60.
    for process in plan(DEMO):
        if "PRACTICE_DIR" in process.env:
            assert process.env["REPORT_CHECK_SECONDS"] == "5", process.name
    (reports,) = [
        p for p in plan(DEMO) if p.name == "reports huisartsenpraktijk-de-akker"
    ]
    assert reports.command[-2:] == ["check_for_lab_reports", "--repeat"]


def test_each_practice_and_its_hospital_seed_the_same_number_of_patients() -> None:
    from tools.demo import PATIENTS, seed_arguments

    assert [PATIENTS[cycle] for cycle in PATIENTS] == [40, 24, 12]
    for partition, cycle in enumerate(PATIENTS):
        arguments = seed_arguments(partition, Path("nhanes.csv"))
        assert arguments[arguments.index("--patients") + 1] == str(PATIENTS[cycle])


def test_up_refuses_while_a_demo_runs(tmp_path: Path) -> None:
    import pytest

    from tools.demo import up

    with pytest.raises(SystemExit, match="already running"):
        up(tmp_path, demo_running=lambda: True)
    assert not any(tmp_path.iterdir())
