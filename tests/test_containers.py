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
from typing import Any

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
        pytest.fail("No Docker engine answers: start Docker (OrbStack on a Mac).")
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
# A web app's certificate names localhost (and <party>.localhost); the probe
# reaches the app by its network name and verifies the certificate as localhost.
FETCH = """
import http.client, json, re, socket, ssl, sys
host = sys.argv[1]
context = ssl.create_default_context(cafile="/browser-ca/ca.crt")
def get(path, secure=True):
    try:
        raw = socket.create_connection((host, 8000), timeout=5)
        connection = http.client.HTTPConnection(host, 8000, timeout=5)
        connection.sock = context.wrap_socket(raw, server_hostname="localhost") if secure else raw
        connection.request("GET", path, headers={"Host": "localhost"})
        response = connection.getresponse()
        return response.status, response.getheader("Content-Type"), response.read()
    except (OSError, http.client.HTTPException) as error:
        return None, type(error).__name__, b""
status, _, page = get("/login/")
stylesheet = re.search(rb'href="(/static/[^"]+[.]css)"', page)
css = get(stylesheet[1].decode()) if stylesheet else (None, None, b"")
plain = get("/login/", secure=False)
print(json.dumps({"login": status, "css": [css[0], css[1]], "plain": plain[0]}))
"""

# Which of a server's ports answer, from wherever the probe runs.
PORTS = """
import json, socket, sys
host = sys.argv[1]
answers = {}
for port in map(int, sys.argv[2:]):
    try:
        socket.create_connection((host, port), timeout=5).close()
        answers[port] = "open"
    except OSError as error:
        answers[port] = type(error).__name__
print(json.dumps(answers))
"""

# Not UZ Leuven, whose web.sqlite3 is the probe's bait, not a database.
APP_HOSPITAL = "az-diest"
APP_PRACTICE = "huisartsenpraktijk-de-ceder"


def probe(compose: Compose, service_name: str, script: str, *args: str) -> Any:
    """Run `script` in a new container of `service_name`, on its networks,
    with the browser CA at /browser-ca; its last line of output, as JSON."""
    services = json.loads(compose("config", "--format", "json").stdout)["services"]
    authority = Path(services["prepare"]["volumes"][0]["source"]) / "browser-ca"
    result = compose(
        "run",
        "--rm",
        "--no-deps",
        "-v",
        f"{authority}:/browser-ca:ro",
        "--entrypoint",
        "python",
        service_name,
        "-c",
        script,
        *args,
    )
    return json.loads(result.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def hospital_app(compose: Compose) -> str:
    """AZ Diest's web app running: its pages and its lab-order endpoint."""
    compose(
        "run",
        "--rm",
        "--no-deps",
        "--entrypoint",
        "python",
        "prepare",
        "-c",
        "from pathlib import Path; from tools.certificates import issue, make_authority;"
        " from tools.demo import hospital_dir, lab_orders_host, prepare_browser;"
        " prepare_browser(Path('/demo'));"
        f" hospital = hospital_dir(Path('/demo'), {APP_HOSPITAL!r});"
        f" authority = make_authority(hospital / 'ca', 'AZ Diest');"
        f" issue(authority, hospital / 'messaging', lab_orders_host({APP_HOSPITAL!r}), server=True)",
    )
    name = f"{APP_HOSPITAL}-web"
    compose("run", "--rm", "--no-deps", name, "python", "manage.py", "migrate", "-v0")
    compose("up", "--detach", "--no-deps", "--no-build", name)
    # Both servers take a moment to start.
    deadline = time.monotonic() + 120
    ports = {"8000": "", "8441": ""}
    while set(ports.values()) != {"open"}:
        assert time.monotonic() < deadline, (ports, compose("logs", name).stdout)
        time.sleep(2)
        ports = probe(compose, name, PORTS, f"{APP_HOSPITAL}-pages", "8000") | probe(
            compose, f"{APP_PRACTICE}-web", PORTS, f"{APP_HOSPITAL}-lab-orders", "8441"
        )
    return name


def test_the_web_app_serves_its_pages_and_stylesheets_over_https_only(
    compose: Compose, hospital_app: str
) -> None:
    report = probe(compose, hospital_app, FETCH, f"{APP_HOSPITAL}-pages")
    assert report["login"] == 200, report
    assert report["css"][0] == 200
    assert report["css"][1].startswith("text/css")
    assert report["plain"] is None


def test_the_practice_reaches_its_hospitals_lab_orders_and_not_its_pages(
    compose: Compose, hospital_app: str
) -> None:
    # One container serves both (R21, DF23, DF25): from the crossing, only 8441.
    host = f"{APP_HOSPITAL}-lab-orders"
    answers = probe(compose, f"{APP_PRACTICE}-web", PORTS, host, "8441", "8000")
    assert answers == {"8441": "open", "8000": "ConnectionRefusedError"}


# Runs on a hospital's network: asks the proxy for a name by SNI, verifies the
# certificate it gets against the browser CA, and reads the response's status.
THROUGH_PROXY = """
import json, socket, ssl, sys
proxy, name = sys.argv[1], sys.argv[2]
context = ssl.create_default_context(cafile="/browser-ca/ca.crt")
try:
    with socket.create_connection((proxy, 8443), timeout=10) as raw:
        with context.wrap_socket(raw, server_hostname=name) as tls:
            tls.sendall(f"GET /login/ HTTP/1.1\\r\\nHost: {name}\\r\\nConnection: close\\r\\n\\r\\n".encode())
            status = tls.recv(64).split()[1].decode()
except OSError as error:
    status = type(error).__name__
print(json.dumps(status))
"""


def test_the_proxy_routes_a_partys_name_to_its_web_app_without_decrypting(
    compose: Compose, compose_folder: Path, hospital_app: str
) -> None:
    # compose.yaml mounts it relative to the project folder, here a temporary one.
    (compose_folder / "docker").mkdir(exist_ok=True)
    shutil.copy(ROOT / "docker" / "sni-proxy.conf", compose_folder / "docker")
    # Not `up`: run publishes no port, so a demo running on 443 is no matter.
    proxy = f"proxy-{uuid.uuid4().hex[:8]}"
    compose("run", "--detach", "--no-deps", "--name", proxy, "proxy")

    def ask(server_name: str) -> str:
        status: str = probe(compose, hospital_app, THROUGH_PROXY, proxy, server_name)
        return status

    # The proxy takes a moment to start; until then no 200.
    deadline = time.monotonic() + 120
    while (status := ask(f"{APP_HOSPITAL}.localhost")) != "200":
        assert time.monotonic() < deadline, status
        time.sleep(2)
    # A name the proxy does not route gets no web app at all.
    assert ask("bank.example") != "200"
