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
            if process.name.split()[1] == hospital_slug(practice):
                assert process.env["MESSAGING_ADDRESS"] == address, process.name
