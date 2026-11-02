"""Only the hospitals' registered SuperNodes join the federation (spec R27, O20)."""

import json
import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

import pytest

from iron_deficiency.dataset import HOSPITALS, hospital_slug
from tools import demo
from tools import certificates

DEMO = Path("/demo")
HOSPITAL_SLUGS = sorted(hospital_slug(name) for name in HOSPITALS.values())
# Flower's exit code for a SuperNode the SuperLink does not admit; it logs
# it, and the process itself exits with 1.
NOT_ADMITTED = "Exit Code: 305"
FLWR = Path(sys.executable).parent / "flwr"


def by_name(demo_dir: Path) -> dict[str, demo.Process]:
    return {process.name: process for process in demo.plan(demo_dir)}


def test_the_superlink_admits_only_registered_supernodes() -> None:
    assert "--enable-supernode-auth" in by_name(DEMO)["superlink"].command


@pytest.mark.parametrize("slug", HOSPITAL_SLUGS)
def test_each_supernode_signs_in_with_its_hospitals_own_key(slug: str) -> None:
    command = by_name(DEMO)[f"supernode {slug}"].command
    key = command[command.index("--auth-supernode-private-key") + 1]
    assert key == str(demo.supernode_key(demo.hospital_dir(DEMO, slug)))


def test_each_hospital_keeps_its_private_key_and_hands_the_startup_its_public_one(
    tmp_path: Path,
) -> None:
    demo.prepare_flower(tmp_path)
    for slug in HOSPITAL_SLUGS:
        key = demo.supernode_key(demo.hospital_dir(tmp_path, slug))
        assert key.stat().st_mode & 0o777 == 0o600
        registered = demo.registered_key(tmp_path, slug)
        assert registered.read_bytes() == key.with_suffix(".pub").read_bytes()
    startup = demo.startup_dir(tmp_path)
    assert all(path.suffix == ".pub" for path in (startup / "supernodes").iterdir())


def test_preparing_again_keeps_each_hospitals_key(tmp_path: Path) -> None:
    demo.prepare_flower(tmp_path)
    key = demo.supernode_key(demo.hospital_dir(tmp_path, HOSPITAL_SLUGS[0]))
    first = key.read_bytes()
    demo.prepare_flower(tmp_path)
    assert key.read_bytes() == first


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
        return port


@contextmanager
def started(process: demo.Process) -> Iterator[subprocess.Popen[bytes]]:
    """Run a demo process, logging to its folder, and stop it afterwards."""
    # The SuperLink and SuperNodes start flower-superexec from PATH.
    path = f"{Path(sys.executable).parent}{os.pathsep}{os.environ['PATH']}"
    with (process.folder / f"{process.name.split()[0]}.out").open("wb") as output:
        child = subprocess.Popen(
            process.command,
            env={**os.environ, **process.env, "PATH": path},
            stdout=output,
            stderr=subprocess.STDOUT,
        )
        try:
            yield child
        finally:
            child.terminate()
            child.wait()


def online_nodes(demo_dir: Path) -> int:
    listing = subprocess.run(
        [str(FLWR), "supernode", "list", "demo", "--format", "json"],
        env={**os.environ, "FLWR_HOME": str(demo.startup_dir(demo_dir) / "flwr-home")},
        capture_output=True,
        text=True,
        check=True,
    )
    nodes = json.loads(listing.stdout)["nodes"]
    return sum(node["status"] == "online" for node in nodes)


def node_as(process: demo.Process, name: str, key: Path | None) -> demo.Process:
    """The same SuperNode on another port, signing in with `key`, or with none."""
    command = list(process.command)
    position = command.index("--auth-supernode-private-key")
    del command[position : position + 2]
    if key is not None:
        command += ["--auth-supernode-private-key", str(key)]
    command[command.index("--port") + 1] = str(free_port())
    return replace(process, name=name, command=command)


def test_the_superlink_admits_a_registered_hospital_and_refuses_any_other_node(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(demo, "SUPERLINK", f"127.0.0.1:{free_port()}")
    monkeypatch.setattr(demo, "FIRST_RUNTIME_PORT", free_port())
    demo.prepare_flower(tmp_path)
    processes = by_name(tmp_path)
    hospital = processes[f"supernode {HOSPITAL_SLUGS[0]}"]
    stranger_key = certificates.make_key_pair(tmp_path / "stranger")
    with started(processes["superlink"]):
        demo.register_supernodes(tmp_path)
        # Registering again, as every `up` does, keeps the registration.
        demo.register_supernodes(tmp_path)
        with (
            started(hospital) as admitted,
            started(node_as(hospital, "stranger", stranger_key)) as stranger,
            started(node_as(hospital, "keyless", None)) as keyless,
        ):
            for name, node in (("stranger", stranger), ("keyless", keyless)):
                assert node.wait(timeout=60) != 0, name
                log = (hospital.folder / f"{name}.out").read_text()
                assert NOT_ADMITTED in log, log[-2000:]
            deadline = time.monotonic() + 60
            while online_nodes(tmp_path) < 1 and time.monotonic() < deadline:
                time.sleep(1)
            assert admitted.poll() is None
            assert online_nodes(tmp_path) == 1
