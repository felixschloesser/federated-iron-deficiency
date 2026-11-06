"""The running containers keep the trust boundaries: the container-backed
scenarios of features/quality/, and the checks beside them.

One compose project in a temporary demo folder: the SuperLink, and UZ Leuven's
SuperNode and ClientApp. Needs a running Docker engine.
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
from pytest_bdd import given, parsers, scenario, then, when

ROOT = Path(__file__).resolve().parents[2]
HOSPITAL = "uz-leuven"

Compose = Callable[..., subprocess.CompletedProcess[str]]
# Each compose fixture's project name, for the checks that look at Docker itself.
PROJECT: dict[Compose, str] = {}
# One file for every worktree: their container runs share one Docker engine.
LOCK = Path(tempfile.gettempdir()) / "iron-deficiency-containers.lock"


def engine_running() -> bool:
    return (
        subprocess.run(["docker", "info"], capture_output=True, check=False).returncode
        == 0
    )


@pytest.fixture(scope="module")
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


@pytest.fixture(scope="module")
def compose(
    tmp_path_factory: pytest.TempPathFactory, engine_to_itself: None
) -> Iterator[Compose]:
    """A compose project of its own, built from this checkout, in a temporary folder."""
    if not engine_running():
        pytest.fail("No Docker engine answers: start Docker (OrbStack on a Mac).")
    folder = tmp_path_factory.mktemp("compose")
    (folder / "demo").mkdir()
    # The proxy joins every party's network in the demo; here only the hospital
    # under test, so the project takes the networks it tests and no more.
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
        # Its own images, named after the project: no other build replaces them.
        # From demo/, where the compose file's build contexts point.
        subprocess.run(
            ["docker", "compose", "-p", name, "-f", str(ROOT / "demo" / "compose.yaml")]
            + ["build"],
            cwd=ROOT / "demo",
            capture_output=True,
            check=True,
            timeout=900,
        )
        start(run, folder)
        yield run
    finally:
        run("down", "--volumes", "--remove-orphans", check=False)
        built = [f"{name}-{image}" for image in ("web", "practice-web", "superexec")]
        subprocess.run(
            ["docker", "image", "rm", *built], capture_output=True, check=False
        )


@pytest.fixture(scope="module")
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


def synthetic_cohort(hospital: str) -> str:
    """Python that gives a hospital a synthetic cohort the real ClientApp trains
    on, and an empty screening-models folder: random values in the real columns,
    both labels; what a model learns from it is no matter."""
    return (
        f"; hospital = Path('/demo/hospitals/{hospital}');"
        " (hospital / 'screening-models').mkdir(exist_ok=True);"
        " import numpy as np, pandas as pd; from datasets import Dataset;"
        " from ml.cohort import FEATURES; rng = np.random.default_rng(0);"
        " frame = pd.DataFrame(rng.normal(size=(300, len(FEATURES))), columns=FEATURES);"
        " frame['iron_deficient'] = rng.integers(0, 2, size=300);"
        " Dataset.from_pandas(frame).save_to_disk(hospital / 'cohort')"
    )


def start(run: Compose, folder: Path) -> None:
    """Flower's part of `prepare`, then the SuperLink and one hospital."""
    # Into the party volumes, through prepare, which hands them to the demo user.
    # What the hospital holds beside the cohort; the ClientApp must see none of it.
    run(
        "run",
        "--rm",
        "--no-deps",
        "prepare",
        "python",
        "-c",
        "from pathlib import Path; from demo.demo import prepare_flower;"
        " prepare_flower(Path('/demo'))"
        + synthetic_cohort(HOSPITAL)
        + f"; (Path('/demo/hospitals/{HOSPITAL}') / 'web.sqlite3').write_text('lab orders')",
    )
    up(run, "flower-superlink")
    run(
        "up",
        "--detach",
        "--no-deps",
        "--no-build",
        # With process isolation the SuperLink runs no ServerApp itself.
        "flower-server-app",
        f"{HOSPITAL}-flower-supernode",
        f"{HOSPITAL}-flower-client-app",
    )


def up(run: Compose, service: str) -> None:
    """Start one service and wait until its health check passes."""
    run(
        "up",
        "--detach",
        "--wait",
        "--wait-timeout",
        "240",
        "--no-deps",
        "--no-build",
        service,
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
        assert time.monotonic() < deadline, run(
            "logs", f"{HOSPITAL}-flower-supernode"
        ).stdout
        time.sleep(2)


@scenario(
    "quality/client_app_isolation.feature",
    "The startup's running code finds only the cohort and reaches nothing",
)
def test_the_startups_running_code_finds_only_the_cohort_and_reaches_nothing() -> None:
    pass


@given("the SuperLink and UZ Leuven's SuperNode and ClientApp are running")
def flower_running(compose: Compose) -> None:
    wait_until_online(compose)


@given("UZ Leuven's folder holds a database beside the cohort")
def bait() -> None:
    """start() wrote web.sqlite3 beside the cohort, for the probe to miss."""


@when(
    "the data scientist runs an app that lists every file it can read "
    "and every address it can reach",
    target_fixture="probe_report",
)
def run_probe(compose: Compose, tmp_path: Path) -> dict[str, Any]:
    probe = tmp_path / "probe"
    shutil.copytree(ROOT / "tests" / "containers" / "probe", probe)
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
    report: dict[str, Any] = json.loads(line.split("PROBE ", 1)[1])
    assert report["hospital"] == HOSPITAL
    return report


@then("the only files it finds are the cohort's")
def only_the_cohort(probe_report: dict[str, Any]) -> None:
    cohort = f"/demo/hospitals/{HOSPITAL}/cohort/"
    assert probe_report["files"]
    assert all(path.startswith(cohort) for path in probe_report["files"])


@then("it reaches no address")
def reaches_nothing(probe_report: dict[str, Any]) -> None:
    assert probe_report["reachable"] == []


# Runs inside the web app's own container: asks the app as compose.yaml starts
# it for its login page and that page's stylesheet, over plain HTTP.
FETCH = """
import http.client, json, re, sys
host = sys.argv[1]
def get(path):
    try:
        connection = http.client.HTTPConnection(host, 8000, timeout=5)
        connection.request("GET", path, headers={"Host": "localhost"})
        response = connection.getresponse()
        return response.status, response.getheader("Content-Type"), response.read()
    except (OSError, http.client.HTTPException) as error:
        return None, type(error).__name__, b""
status, _, page = get("/login/")
stylesheet = re.search(rb'href="(/static/[^"]+[.]css)"', page)
css = get(stylesheet[1].decode()) if stylesheet else (None, None, b"")
print(json.dumps({"login": status, "css": [css[0], css[1]], "stylesheet": stylesheet[1].decode() if stylesheet else None, "page": page.decode(errors="replace")[:2000] if css[0] != 200 else ""}))
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


@pytest.fixture(scope="module")
def hospital_app(compose: Compose) -> str:
    """AZ Diest's web app running: its pages and its lab-order endpoint."""
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
        " (hospital / 'screening-models').mkdir(exist_ok=True)",
    )
    name = f"{APP_HOSPITAL}-web"
    compose("run", "--rm", "--no-deps", name, "python", "manage.py", "migrate", "-v0")
    # Healthy once both its servers answer (its health check).
    up(compose, name)
    return name


@scenario(
    "quality/web_apps.feature",
    "A hospital's web app serves its pages and stylesheets with DEBUG off",
)
def test_a_hospitals_web_app_serves_its_pages_and_stylesheets() -> None:
    pass


@given(
    "AZ Diest's web app is running as compose.yaml starts it", target_fixture="web_app"
)
def web_app(hospital_app: str) -> str:
    return hospital_app


@when(
    "a browser asks it for the login page and that page's stylesheet",
    target_fixture="fetched",
)
def fetch(compose: Compose, web_app: str) -> dict[str, Any]:
    report: dict[str, Any] = probe(compose, web_app, FETCH, f"{APP_HOSPITAL}-pages")
    return report


@then('both answer 200, the stylesheet as "text/css"')
def both_answer(fetched: dict[str, Any]) -> None:
    assert fetched["login"] == 200, fetched
    # On a failure, which stylesheet it asked for and the page it got.
    assert fetched["css"][0] == 200, fetched
    assert fetched["css"][1].startswith("text/css"), fetched


def test_the_practice_reaches_its_hospitals_messaging_and_not_its_pages(
    compose: Compose, hospital_app: str
) -> None:
    # One container serves both (features/quality/party_isolation.feature, DF23, DF25): from the crossing, only 8441.
    host = f"{APP_HOSPITAL}-messaging"
    answers = probe(compose, f"{APP_PRACTICE}-web", PORTS, host, "8441", "8000")
    assert answers == {"8441": "open", "8000": "ConnectionRefusedError"}


# Runs on a hospital's network: asks the proxy for a name by Host header and
# reads the response's status.
THROUGH_PROXY = """
import http.client, json, sys
proxy, name = sys.argv[1], sys.argv[2]
try:
    connection = http.client.HTTPConnection(proxy, 8080, timeout=10)
    connection.request("GET", "/login/", headers={"Host": name})
    status = str(connection.getresponse().status)
except (OSError, http.client.HTTPException) as error:
    status = type(error).__name__
print(json.dumps(status))
"""


def test_the_proxy_routes_a_partys_name_to_its_web_app(
    compose: Compose, compose_folder: Path, hospital_app: str
) -> None:
    # compose.yaml mounts it relative to the project folder, here a temporary one.
    shutil.copy(ROOT / "demo" / "proxy.conf", compose_folder / "demo")
    up(compose, "proxy")

    def ask(server_name: str) -> str:
        status: str = probe(compose, hospital_app, THROUGH_PROXY, "proxy", server_name)
        return status

    assert ask(f"{APP_HOSPITAL}.localhost") == "200"
    # A name the proxy does not route gets no web app at all.
    assert ask("bank.example") != "200"
    # Every service under test is up now: the project holds only the networks
    # they need, so it shares Docker's address pool with a running demo.
    listing = subprocess.run(
        ["docker", "network", "ls", "--format", "{{.Name}}", "--filter"]
        + [f"label=com.docker.compose.project={PROJECT[compose]}"],
        capture_output=True,
        text=True,
        check=True,
    )
    project = PROJECT[compose]
    assert set(listing.stdout.split()) == {
        f"{project}_{network}"
        for network in (
            "setup",
            "startup",
            "model-updates",
            f"{HOSPITAL}-flower-client-app",
            APP_HOSPITAL,
            "messaging",
            APP_PRACTICE,
        )
    }


# Runs on the hospital's network and talks to both parties only through the
# proxy, as a browser would: their login forms, CSRF tokens and POST forms,
# one cookie jar per party. Prints what each step showed.
END_TO_END = r"""
import http.cookiejar, json, re, sys, urllib.parse, urllib.request
proxy, hospital, practice, password, laboratory = sys.argv[1:6]

class Party:
    def __init__(self, host):
        self.host = host
        jar = urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
        self.opener = urllib.request.build_opener(jar)

    def open(self, path, data=None):
        request = urllib.request.Request(
            f"http://{proxy}:8080{path}", data=data, headers={"Host": self.host}
        )
        with self.opener.open(request, timeout=30) as response:
            return urllib.parse.urlsplit(response.geturl()).path, response.read().decode()

    def get(self, path):
        return self.open(path)

    def post(self, path, page, **fields):
        token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page)[1]
        data = urllib.parse.urlencode({"csrfmiddlewaretoken": token, **fields})
        return self.open(path, data.encode())

    def log_in(self, username):
        _, page = self.get("/login/")
        return self.post("/login/", page, username=username, password=password)

seen = {}
doctor, lab = Party(f"{practice}.localhost"), Party(f"{hospital}.localhost")
doctor.log_in("doctor")
_, patients = doctor.get("/practice/patients/")
patient = re.search(r'href="(/practice/patients/\d+/)"', patients)[1]
_, page = doctor.get(patient)
# One laboratory: Collect sample is a button, and leads to the CBC order.
order_page, page = doctor.post(f"{patient}collect-sample/", page)
seen["order_page"] = order_page
back, page = doctor.post(order_page, page, indication="other")
seen["ordered"] = back == patient and "Awaiting lab report" in page
seen["sent_to"] = laboratory in page

lab.log_in("staff")
_, to_analyse = lab.get("/lab/test-requests/")
analyse = re.search(r'action="(/lab/test-requests/\d+/analyse/)"', to_analyse)[1]
lab.post(analyse, to_analyse)
_, analysed = lab.get("/lab/test-requests/analysed/")
seen["analysed"] = "not screened" in analysed.lower()

_, page = doctor.get(patient)
back, page = doctor.post(f"{patient}check-for-reports/", page)
seen["fetched"] = back == patient and "1 new lab report." in page
seen["released"] = "Lab report released" in page
print(json.dumps(seen))
"""


def test_a_cbc_goes_from_the_practice_to_the_laboratory_and_back(
    compose: Compose, hospital_app: str, tmp_path: Path
) -> None:
    from tests.conftest import nhanes_rows
    from web.seeding.accounts import PASSWORD

    # The same participants at both parties, from a small NHANES file, so no
    # download: what prepare does for the demo, for one hospital and its practice.
    csv = tmp_path / "nhanes.csv"
    nhanes_rows().to_csv(csv, index=False)
    practice = f"{APP_PRACTICE}-web"
    seeding = ["run", "--rm", "--no-deps", "-e", "DJANGO_DEBUG=1"]
    nhanes = ["-v", f"{csv}:/tmp/nhanes.csv:ro"]
    seed = ["--seed", "0", "--nhanes", "/tmp/nhanes.csv"]
    manage = ["python", "manage.py"]
    compose(*seeding, *nhanes, hospital_app, *manage, "seed_hospital", *seed)
    # As prepare does: the hospital knows the practice by its folder name.
    known = ["add_practice", APP_PRACTICE, "Huisartsenpraktijk De Ceder"]
    compose(*seeding, hospital_app, *manage, *known)
    # As prepare does: the practice's own image serves it, without the seeding.
    as_practice = [
        *seeding,
        *("-e", "PARTY=practice"),
        *("-e", f"DATA_DIR=/demo/practices/{APP_PRACTICE}"),
    ]
    compose(*as_practice, "prepare", *manage, "migrate", "-v0")
    compose(*as_practice, *nhanes, "prepare", *manage, "seed_practice", *seed)
    address = f"{APP_HOSPITAL}-messaging:8441"
    compose(*as_practice, "prepare", *manage, "add_laboratory", "AZ Diest", address)
    up(compose, practice)
    up(compose, "proxy")
    seen = probe(
        compose,
        hospital_app,
        END_TO_END,
        "proxy",
        APP_HOSPITAL,
        APP_PRACTICE,
        PASSWORD,
        "AZ Diest",
    )
    assert seen["order_page"].endswith("/orders/cbc/"), seen
    assert seen["ordered"], seen
    assert seen["sent_to"], seen
    assert seen["analysed"], seen
    assert seen["fetched"], seen
    assert seen["released"], seen


# Runs in the startup's web app's container: does it reach the SuperLink, and
# what does it see of the SuperLink's state.
STARTUP_SIGHT = """
import json, os, socket
try:
    socket.create_connection(("flower-superlink", 9092), timeout=5).close()
    superlink = "open"
except OSError as error:
    superlink = type(error).__name__
print(json.dumps({"superlink": superlink, "state": os.listdir("/demo/startup/superlink")}))
"""


def test_the_startups_web_app_reaches_the_superlink_but_not_its_state(
    compose: Compose,
) -> None:
    # Last: it adds the startup-web network, which the listing above leaves out.
    report = probe(compose, "startup-web", STARTUP_SIGHT)
    assert report == {"superlink": "open", "state": []}


@scenario("final_model_journey.feature", "Train, release, fetch, fetch again")
def test_train_release_fetch_fetch_again() -> None:
    pass


def flower_run(compose: Compose, configuration: str) -> str:
    """Submit a run of the app as the data scientist; wait until it finishes and
    return its ID, failing unless it completed."""
    submitted = json.loads(
        flwr(
            compose,
            "train",
            "flwr",
            "run",
            "/app",
            "demo",
            "--run-config",
            f"demo-dir='/demo' {configuration}",
            "--format",
            "json",
        )
    )
    run_id = str(submitted["run-id"])
    deadline = time.monotonic() + 240
    while True:
        listing = flwr(
            compose,
            "train",
            "flwr",
            "ls",
            "demo",
            "--run-id",
            run_id,
            "--format",
            "json",
        )
        (run,) = json.loads(listing)["runs"]
        if run["status"].startswith("finished"):
            break
        assert time.monotonic() < deadline, (
            run["status"],
            compose("logs", "flower-server-app").stdout[-2000:],
            compose("logs", f"{HOSPITAL}-flower-client-app").stdout[-2000:],
        )
        time.sleep(3)
    assert run["status"] == "finished:completed", (
        run,
        compose("logs", "flower-server-app").stdout[-3000:],
    )
    return run_id


def folders(compose: Compose) -> dict[str, Any]:
    """What the startup and UZ Leuven hold: each file's name and SHA-256."""
    script = (
        "import hashlib, json; from pathlib import Path;"
        " held = lambda folder: {path.name: hashlib.sha256(path.read_bytes()).hexdigest()"
        " for path in sorted(Path(folder).glob('*.pt'))};"
        " print(json.dumps({'startup': held('/demo/startup/final-models'),"
        f" 'hospital': held('/demo/hospitals/{HOSPITAL}/screening-models')}}))"
    )
    result = compose("run", "--rm", "--no-deps", "prepare", "python", "-c", script)
    held: dict[str, Any] = json.loads(result.stdout.strip().splitlines()[-1])
    return held


@pytest.fixture
def journey() -> dict[str, Any]:
    return {}


# FedAvg trains only with at least two hospitals available.
SECOND_HOSPITAL = "heilig-hart-leuven"


@given(
    "Heilig Hart Leuven's SuperNode and ClientApp too, as FedAvg trains only with"
    " two hospitals"
)
def second_hospital(compose: Compose) -> None:
    compose(
        "run",
        "--rm",
        "--no-deps",
        "prepare",
        "python",
        "-c",
        "from pathlib import Path" + synthetic_cohort(SECOND_HOSPITAL),
    )
    compose(
        "up",
        "--detach",
        "--no-deps",
        "--no-build",
        f"{SECOND_HOSPITAL}-flower-supernode",
        f"{SECOND_HOSPITAL}-flower-client-app",
    )
    deadline = time.monotonic() + 120
    while online_nodes(compose) < 2:
        assert time.monotonic() < deadline, "the second hospital did not come online"
        time.sleep(2)


@when("the data scientist trains for one round")
def train_one_round(compose: Compose, journey: dict[str, Any]) -> None:
    journey["training"] = flower_run(compose, "num-server-rounds=1")


@then("the startup keeps the run's final model and UZ Leuven stores none")
def kept_not_stored(compose: Compose, journey: dict[str, Any]) -> None:
    held = folders(compose)
    assert f"{journey['training']}.pt" in held["startup"], held
    assert held["hospital"] == {}, held


# As prepare does for the demo: the startup's web app, migrated, with its data
# scientist, knowing UZ Leuven as a recipient hospital by its folder's name.
RELEASE = """
from django.utils import timezone
from web.accounts.models import User
from web.startup.training.models import Release
Release.objects.release(
    final_model_run_id={run_id!r},
    released_by=User.objects.get(username="data-scientist"),
    now=timezone.now(),
)
"""

# What the laboratory director's Fetch new final models runs, in UZ Leuven's
# own web app container, on the final-models network; the run IDs it stored.
FETCH_FINAL_MODELS = """
import json
from django.utils import timezone
from web.hospital.deployment.fetching import fetch_final_models
print(json.dumps(fetch_final_models(now=timezone.now())))
"""


@when("the data scientist releases that final model")
def release(compose: Compose, journey: dict[str, Any]) -> None:
    seeding = ["run", "--rm", "--no-deps", "-e", "DJANGO_DEBUG=1", "startup-web"]
    manage = ["python", "manage.py"]
    compose(*seeding, *manage, "migrate", "-v0")
    compose(*seeding, *manage, "seed_startup")
    compose(*seeding, *manage, "add_hospital", HOSPITAL, "UZ Leuven")
    up(compose, "startup-web")
    release_one = RELEASE.format(run_id=journey["training"])
    compose(*seeding, *manage, "shell", "-c", release_one)


@then("UZ Leuven still stores none")
def still_none(compose: Compose) -> None:
    assert folders(compose)["hospital"] == {}


@when(parsers.re("UZ Leuven fetches new final models(?: again)?"))
def hospital_fetches(compose: Compose, journey: dict[str, Any]) -> None:
    journey["before"] = folders(compose)["hospital"]
    result = compose(
        "run",
        "--rm",
        "--no-deps",
        f"{HOSPITAL}-web",
        "python",
        "manage.py",
        "shell",
        "-c",
        FETCH_FINAL_MODELS,
    )
    journey["fetched"] = json.loads(result.stdout.strip().splitlines()[-1])


@then(
    "UZ Leuven stores the final model under the training run's ID, with its local"
    " validation"
)
def stored(compose: Compose, journey: dict[str, Any]) -> None:
    assert journey["fetched"] == [journey["training"]]
    held = folders(compose)["hospital"]
    assert list(held) == [f"{journey['training']}.pt"], held
    path = f"/demo/hospitals/{HOSPITAL}/screening-models/{journey['training']}.pt"
    script = (
        "from pathlib import Path; from ml.final_model import read;"
        f" model = read(Path({path!r}));"
        " print(model.problem() is None and bool(model.confusion_matrices))"
    )
    result = compose("run", "--rm", "--no-deps", "prepare", "python", "-c", script)
    assert result.stdout.strip().splitlines()[-1] == "True"


@then("it fetches none and UZ Leuven's copy is unchanged")
def unchanged(compose: Compose, journey: dict[str, Any]) -> None:
    assert journey["fetched"] == []
    assert folders(compose)["hospital"] == journey["before"]
