"""One compose project of the demo for the tests that need a Docker engine
(tests/e2e/, the running containers in tests/quality/), in a temporary demo
folder. A test starts only what it needs: each fixture builds its own images
and starts its own services, once per test run.
"""

import fcntl
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
# The hospital whose SuperNode and ClientApp the Flower tests start.
HOSPITAL = "uz-leuven"
# Not UZ Leuven, whose shared.sqlite3 is the ClientApp probe's bait, not a database.
APP_HOSPITAL = "az-diest"
APP_PRACTICE = "huisartsenpraktijk-de-ceder"

Compose = Callable[..., subprocess.CompletedProcess[str]]
# Each compose fixture's project name, for the checks that look at Docker itself.
PROJECT: dict[Compose, str] = {}
# One file for every worktree: their container runs share one Docker engine.
LOCK = Path(tempfile.gettempdir()) / "iron-deficiency-containers.lock"
# The images compose.yaml builds.
IMAGES = ("web", "practice-web", "superexec")
# Each project's images built so far: a test run builds each once.
BUILT: dict[str, set[str]] = {}


def engine_running() -> bool:
    return (
        subprocess.run(["docker", "info"], capture_output=True, check=False).returncode
        == 0
    )


@pytest.fixture(scope="session")
def engine_to_itself() -> Iterator[None]:
    """Wait until no other worktree's container run uses the engine: parallel
    builds and cohorts slow every one of them past its timeouts."""
    with LOCK.open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            # Past pytest's capture, so a wait never looks like a hang.
            print(f"Waiting for another container run ({LOCK})", file=sys.__stderr__)
            fcntl.flock(lock, fcntl.LOCK_EX)
        yield


@pytest.fixture(scope="session")
def compose(
    tmp_path_factory: pytest.TempPathFactory, engine_to_itself: None
) -> Iterator[Compose]:
    """A compose project of its own, from this checkout, in a temporary folder:
    nothing built and nothing running until a fixture asks for it."""
    if not engine_running():
        pytest.fail("No Docker engine answers: start Docker (OrbStack on a Mac).")
    folder = tmp_path_factory.mktemp("compose")
    (folder / "demo").mkdir()
    # The proxy joins every party's network in the demo; here only the hospital
    # and practice under test, so the project takes the networks it tests.
    override = folder / "demo" / "test-override.yaml"
    override.write_text(
        "services:\n  proxy:\n"
        f"    networks: !override [{APP_HOSPITAL}, {APP_PRACTICE}]\n"
    )
    name = f"test-{uuid.uuid4().hex[:8]}"

    def run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        # A step that hangs fails the test rather than the whole gate.
        return subprocess.run(
            # From folder/demo, so the compose file's ../.demo is folder/.demo.
            [
                "docker",
                "compose",
                "-p",
                name,
                "--project-directory",
                str(folder / "demo"),
            ]
            + ["-f", str(ROOT / "demo" / "compose.yaml"), "-f", str(override), *args],
            capture_output=True,
            text=True,
            check=check,
            timeout=300,
            # Any free port for the proxy, so a running demo on 80 is no matter.
            env={**os.environ, "DEMO_HTTP_PORT": "0"},
        )

    PROJECT[run] = name
    try:
        yield run
    finally:
        run("down", "--volumes", "--remove-orphans", check=False)
        built = [f"{name}-{image}" for image in IMAGES]
        subprocess.run(
            ["docker", "image", "rm", *built], capture_output=True, check=False
        )


def build(compose: Compose, *images: str) -> None:
    """Build these of the project's images, once each, named after the project
    so no other build replaces them; from demo/, where the compose file's build
    contexts point. Each is built by the one service that declares its build."""
    project = PROJECT[compose]
    built = BUILT.setdefault(project, set())
    wanted = set(images) - built
    if not wanted:
        return
    services = json.loads(compose("config", "--format", "json").stdout)["services"]
    builders = [
        name
        for name, spec in services.items()
        if "build" in spec and spec["image"].removeprefix(f"{project}-") in wanted
    ]
    assert len(builders) == len(wanted), (wanted, builders)
    subprocess.run(
        ["docker", "compose", "-p", project]
        + ["-f", str(ROOT / "demo" / "compose.yaml"), "build", *builders],
        cwd=ROOT / "demo",
        capture_output=True,
        check=True,
        timeout=900,
    )
    built.update(wanted)


@pytest.fixture(scope="session")
def compose_folder(compose: Compose) -> Path:
    """The temporary folder the compose project runs in, holding its .demo/."""
    services = json.loads(compose("config", "--format", "json").stdout)["services"]
    (downloads,) = [
        Path(volume["source"])
        for volume in services["prepare"]["volumes"]
        if volume["target"] == "/demo/huggingface"
    ]
    folder = downloads.parent.parent
    # Never the checkout's own .demo/, which holds the user's downloads and CA.
    assert folder != ROOT and ROOT not in folder.parents, folder
    return folder


def up(compose: Compose, service: str) -> None:
    """Start one service and wait until its health check passes."""
    compose(
        "up",
        "--detach",
        "--wait",
        "--wait-timeout",
        "240",
        "--no-deps",
        "--no-build",
        service,
    )


def synthetic_cohort(hospital: str) -> str:
    """Python that gives a hospital a synthetic cohort the real ClientApp trains
    on, as if its laboratory director provided it (in a folder of its own, as
    ml.training_cohort writes it), and an empty screening-models folder: random
    values in the real columns, both labels; what a model learns from it is no matter."""
    return (
        f"; hospital = Path('/demo/hospitals/{hospital}');"
        " (hospital / 'screening-models').mkdir(exist_ok=True);"
        " import numpy as np, pandas as pd; from datasets import Dataset;"
        " from ml.cohort import FEATURES; rng = np.random.default_rng(0);"
        " frame = pd.DataFrame(rng.normal(size=(300, len(FEATURES))), columns=FEATURES);"
        " frame['iron_deficient'] = rng.integers(0, 2, size=300);"
        " Dataset.from_pandas(frame).save_to_disk(hospital / 'cohort' / 'synthetic')"
    )


@pytest.fixture(scope="session")
def superlink(compose: Compose) -> None:
    """Flower's part of `prepare`, into the party volumes, then the SuperLink."""
    build(compose, "web")
    compose(
        "run",
        "--rm",
        "--no-deps",
        "prepare",
        "python",
        "-c",
        "from pathlib import Path; from demo.demo import prepare_flower;"
        " prepare_flower(Path('/demo'))",
    )
    up(compose, "flower-superlink")


@pytest.fixture(scope="session")
def flower(compose: Compose, superlink: None) -> None:
    """The SuperLink, the ServerApp, and UZ Leuven's SuperNode and ClientApp; UZ
    Leuven holds a synthetic cohort and, beside it, a database the ClientApp
    must never see."""
    build(compose, "superexec")
    compose(
        "run",
        "--rm",
        "--no-deps",
        "prepare",
        "python",
        "-c",
        "from pathlib import Path"
        + synthetic_cohort(HOSPITAL)
        + f"; (Path('/demo/hospitals/{HOSPITAL}') / 'shared.sqlite3').write_text('lab orders')",
    )
    compose(
        "up",
        "--detach",
        "--no-deps",
        "--no-build",
        # With process isolation the SuperLink runs no ServerApp itself.
        "flower-server-app",
        f"{HOSPITAL}-flower-supernode",
        f"{HOSPITAL}-flower-client-app",
    )


def flwr(compose: Compose, *args: str) -> str:
    """A flwr command as the startup's data scientist, inside TB2."""
    return compose(
        "run",
        "--rm",
        "--no-deps",
        "-e",
        "FLWR_HOME=/demo/startup/flwr-home",
        *args,
    ).stdout


def online_nodes(compose: Compose) -> int:
    listing = flwr(
        compose, "train", "flwr", "supernode", "list", "demo", "--format", "json"
    )
    return sum(node["status"] == "online" for node in json.loads(listing)["nodes"])


def wait_until_online(compose: Compose, nodes: int = 1) -> None:
    deadline = time.monotonic() + 120
    while online_nodes(compose) < nodes:
        assert time.monotonic() < deadline, compose(
            "logs", f"{HOSPITAL}-flower-supernode"
        ).stdout
        time.sleep(2)


@pytest.fixture(scope="session")
def hospital_app(compose: Compose) -> str:
    """AZ Diest's web app running: its pages and its lab-order endpoint."""
    build(compose, "web")
    compose(
        "run",
        "--rm",
        "--no-deps",
        "prepare",
        "python",
        "-c",
        "from pathlib import Path;"
        " from demo.demo import hospital_dir;"
        f" hospital = hospital_dir(Path('/demo'), {APP_HOSPITAL!r});"
        # A volume's subpath must exist before a container mounts it.
        " (hospital / 'screening-models').mkdir(exist_ok=True);"
        # The web app mounts the cohort, read-only, to validate fetched final models.
        " (hospital / 'cohort').mkdir(exist_ok=True)",
    )
    name = f"{APP_HOSPITAL}-web"
    compose("run", "--rm", "--no-deps", name, "python", "manage.py", "migrate", "-v0")
    # Healthy once both its servers answer (its health check).
    up(compose, name)
    return name


def probe(compose: Compose, service_name: str, script: str, *args: str) -> Any:
    """Run `script` in a new container of `service_name`, on its networks; its
    last line of output, as JSON."""
    result = compose(
        "run",
        "--rm",
        "--no-deps",
        "--entrypoint",
        "python",
        service_name,
        "-c",
        script,
        *args,
    )
    return json.loads(result.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="session")
def proxy(compose: Compose, compose_folder: Path, hospital_app: str) -> None:
    """The proxy running, routing to AZ Diest's web app (and De Ceder's, once
    started). compose.yaml mounts its configuration relative to the project
    folder, here a temporary one: copied there first, or Docker would mount a
    directory of that name."""
    shutil.copy(ROOT / "demo" / "proxy.conf", compose_folder / "demo")
    up(compose, "proxy")
