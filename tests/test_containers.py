"""The running containers keep the trust boundaries (spec R27, R28, R29).

One compose project in a temporary demo folder: the SuperLink, the
registration of every hospital's SuperNode, and UZ Leuven's SuperNode and
ClientApp. Needs a running Docker engine.
"""

import json
import shutil
import subprocess
import time
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from tools import certificates

ROOT = Path(__file__).resolve().parents[1]
HOSPITAL = "uz-leuven"
# Flower's exit code for a SuperNode the SuperLink does not admit; it logs it,
# and the container itself exits with 1.
NOT_ADMITTED = "Exit Code: 305"

Compose = Callable[..., subprocess.CompletedProcess[str]]


def engine_running() -> bool:
    return (
        subprocess.run(["docker", "info"], capture_output=True, check=False).returncode
        == 0
    )


@pytest.fixture(scope="module")
def compose(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Compose]:
    """A compose project of its own, built from this checkout, in a temporary folder."""
    if not engine_running():
        pytest.fail("No Docker engine answers: start OrbStack (`orb start`).")
    subprocess.run(
        ["docker", "compose", "build", "prepare", "serverapp"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    )
    folder = tmp_path_factory.mktemp("compose")
    name = f"test-{uuid.uuid4().hex[:8]}"

    def run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        # A step that hangs fails the test rather than the whole gate.
        return subprocess.run(
            ["docker", "compose", "-p", name, "--project-directory", str(folder)]
            + ["-f", str(ROOT / "compose.yaml"), *args],
            capture_output=True,
            text=True,
            check=check,
            timeout=300,
        )

    try:
        start(run, folder)
        yield run
    finally:
        run("down", "--volumes", "--remove-orphans", check=False)


@pytest.fixture(scope="module")
def compose_folder(compose: Compose) -> Path:
    """The temporary folder the compose project runs in, holding its demo/."""
    services = json.loads(compose("config", "--format", "json").stdout)["services"]
    return Path(services["prepare"]["volumes"][0]["source"]).parent


def start(run: Compose, folder: Path) -> None:
    """Flower's part of `prepare`, then the SuperLink, registration and one hospital."""
    run(
        "run",
        "--rm",
        "--no-deps",
        "--entrypoint",
        "python",
        "prepare",
        "-c",
        "from pathlib import Path; from tools.demo import prepare_flower;"
        " prepare_flower(Path('/demo'))",
    )
    hospital = folder / "demo" / "hospitals" / HOSPITAL
    # What the hospital holds beside the cohort; the ClientApp must see none of it.
    (hospital / "cohort").mkdir(parents=True)
    (hospital / "cohort" / "rows.arrow").write_text("cohort")
    (hospital / "final-models").mkdir()
    (hospital / "web.sqlite3").write_text("lab orders")
    run("up", "--detach", "--no-deps", "--no-build", "superlink")
    deadline = time.monotonic() + 120
    while "healthy" not in run("ps", "--format", "{{.Status}}", "superlink").stdout:
        assert time.monotonic() < deadline, run("logs", "superlink").stdout
        time.sleep(2)
    run("run", "--rm", "--no-deps", "register")
    run(
        "up",
        "--detach",
        "--no-deps",
        "--no-build",
        # With process isolation the SuperLink runs no ServerApp itself.
        "serverapp",
        f"{HOSPITAL}-supernode",
        f"{HOSPITAL}-clientapp",
    )


def flwr(run: Compose, *args: str) -> str:
    """A flwr command as the startup's data scientist, inside TB2."""
    return run(
        "run",
        "--rm",
        "--no-deps",
        "-e",
        "FLWR_HOME=/demo/startup/flwr-home",
        *args,
    ).stdout


def online_nodes(run: Compose) -> int:
    listing = flwr(
        run, "train", "flwr", "supernode", "list", "demo", "--format", "json"
    )
    return sum(node["status"] == "online" for node in json.loads(listing)["nodes"])


def wait_until_online(run: Compose) -> None:
    deadline = time.monotonic() + 120
    while online_nodes(run) < 1:
        assert time.monotonic() < deadline, run("logs", f"{HOSPITAL}-supernode").stdout
        time.sleep(2)


def test_the_startups_code_sees_only_the_cohort_and_final_models_and_reaches_nothing(
    compose: Compose, tmp_path: Path
) -> None:
    wait_until_online(compose)
    probe = tmp_path / "probe"
    shutil.copytree(ROOT / "tests" / "probe", probe)
    output = flwr(
        compose,
        "-v",
        f"{probe}:/probe",
        "train",
        "flwr",
        "run",
        "/probe",
        "demo",
        "--stream",
    )
    (line,) = [line for line in output.splitlines() if "PROBE {" in line]
    report = json.loads(line.split("PROBE ", 1)[1])
    assert report["hospital"] == HOSPITAL
    allowed = (
        f"/demo/hospitals/{HOSPITAL}/cohort/",
        f"/demo/hospitals/{HOSPITAL}/final-models/",
    )
    assert report["files"] == [f"/demo/hospitals/{HOSPITAL}/cohort/rows.arrow"]
    assert all(path.startswith(allowed) for path in report["files"])
    assert report["reachable"] == []


def test_the_superlink_admits_the_registered_hospital_and_refuses_any_other_node(
    compose: Compose, tmp_path: Path
) -> None:
    wait_until_online(compose)
    stranger = certificates.make_key_pair(tmp_path / "stranger" / "key")
    supernode = [
        "--superlink=superlink:9092",
        f"--root-certificates=/demo/hospitals/{HOSPITAL}/certificates/ca.crt",
        "--isolation=process",
    ]
    for name, extra in (
        ("stranger", ["-v", f"{stranger.parent}:/stranger:ro"]),
        ("keyless", []),
    ):
        key = (
            ["--auth-supernode-private-key=/stranger/key"] if name == "stranger" else []
        )
        refused = compose(
            "run",
            "--rm",
            "--no-deps",
            *extra,
            f"{HOSPITAL}-supernode",
            *supernode,
            *key,
            check=False,
        )
        assert refused.returncode != 0, name
        assert NOT_ADMITTED in refused.stdout + refused.stderr, name
    # Registering again, as every `up` does, keeps the registration.
    compose("run", "--rm", "--no-deps", "register")
    assert online_nodes(compose) == 1


# Runs inside the web app's own container: starts the app as compose.yaml
# declares it, then asks it for its login page, that page's stylesheet, and
# the login page again over plain HTTP.
FETCH = """
import json, re, ssl, subprocess, sys, time, urllib.error, urllib.request
server = subprocess.Popen(json.loads(sys.argv[1]))
context = ssl.create_default_context(cafile="/browser-ca/ca.crt")
def get(url):
    try:
        with urllib.request.urlopen(url, context=context, timeout=5) as response:
            return response.status, response.headers.get("Content-Type"), response.read()
    except (urllib.error.URLError, OSError) as error:
        return None, type(error).__name__, b""
deadline = time.monotonic() + 60
while get("https://localhost:8000/login/")[0] is None and time.monotonic() < deadline:
    time.sleep(1)
status, _, page = get("https://localhost:8000/login/")
stylesheet = re.search(rb'href="(/static/[^"]+[.]css)"', page)
css = get("https://localhost:8000" + stylesheet[1].decode()) if stylesheet else (None, None, b"")
plain = get("http://localhost:8000/login/")
server.terminate()
print(json.dumps({"login": status, "css": [css[0], css[1]], "plain": plain[0]}))
"""


def test_the_web_app_serves_its_pages_and_stylesheets_over_https_only(
    compose: Compose, compose_folder: Path
) -> None:
    from tests.test_compose import service

    name = f"{HOSPITAL}-web"
    compose(
        "run",
        "--rm",
        "--no-deps",
        "--entrypoint",
        "python",
        "prepare",
        "-c",
        "from pathlib import Path; from tools.demo import prepare_browser;"
        " prepare_browser(Path('/demo'))",
    )
    compose("run", "--rm", "--no-deps", name, "python", "manage.py", "migrate", "-v0")
    authority = compose_folder / "demo" / "browser-ca"
    result = compose(
        "run",
        "--rm",
        "--no-deps",
        "-v",
        f"{authority}:/browser-ca:ro",
        "--entrypoint",
        "python",
        name,
        "-c",
        FETCH,
        json.dumps(service(name)["command"]),
    )
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report["login"] == 200, result.stderr[-2000:]
    assert report["css"][0] == 200
    assert report["css"][1].startswith("text/css")
    assert report["plain"] is None
