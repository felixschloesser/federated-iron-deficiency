"""The demo launcher: one folder and one process per party (spec §9, R21)."""

from pathlib import Path

from iron_deficiency.dataset import HOSPITALS
from tools.demo import plan

DEMO = Path("/demo")


def test_one_superlink_three_supernodes_three_web_apps() -> None:
    names = [process.name for process in plan(DEMO)]
    assert names.count("superlink") == 1
    assert sorted(name for name in names if name.startswith("supernode")) == sorted(
        f"supernode {slug}" for slug in HOSPITALS.values()
    )
    assert sorted(name for name in names if name.startswith("web")) == sorted(
        f"web {slug}" for slug in HOSPITALS.values()
    )


def test_each_hospital_process_sees_only_its_own_folder() -> None:
    for process in plan(DEMO):
        if process.name == "superlink":
            continue
        own = process.name.split()[1]
        text = " ".join([*process.command, *process.env.values()])
        assert str(DEMO / "hospitals" / own) in text
        others = set(HOSPITALS.values()) - {own}
        assert not any(other in text for other in others), process.name
        assert str(DEMO / "startup") not in text.replace(
            str(DEMO / "startup" / "certificates" / "ca.crt"), ""
        ), process.name


def test_the_superlink_keeps_its_state_with_the_startup() -> None:
    (superlink,) = [process for process in plan(DEMO) if process.name == "superlink"]
    text = " ".join([*superlink.command, *superlink.env.values()])
    assert str(DEMO / "startup" / "superlink") in text
    assert "hospitals" not in text


def test_every_flower_connection_uses_tls() -> None:
    for process in plan(DEMO):
        assert "--insecure" not in process.command, process.name


def test_web_apps_listen_on_their_own_ports() -> None:
    ports = {
        process.name: process.command[-1]
        for process in plan(DEMO)
        if process.name.startswith("web")
    }
    assert sorted(ports.values()) == [
        "127.0.0.1:8001",
        "127.0.0.1:8002",
        "127.0.0.1:8003",
    ]
