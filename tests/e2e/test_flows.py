"""End to end through the running demo: a CBC from the practice to the laboratory
and back through the proxy, as a browser; and a final model trained, transmitted
and transmitted again through the real Flower apps (features/transmission.feature).
Every test here needs a Docker engine (tests/e2e/conftest.py)."""

import json
import time
from pathlib import Path
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenario, then, when

from tests.compose_project import (
    APP_HOSPITAL,
    APP_PRACTICE,
    HOSPITAL,
    Compose,
    build,
    flwr,
    online_nodes,
    probe,
    synthetic_cohort,
    up,
    wait_until_online,
)

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
    compose: Compose, hospital_app: str, proxy: None, tmp_path: Path
) -> None:
    build(compose, "practice-web")
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
        *("-e", "DJANGO_SETTINGS_MODULE=web.settings.practice"),
        *("-e", f"DATA_DIR=/demo/practices/{APP_PRACTICE}"),
    ]
    compose(*as_practice, "prepare", *manage, "migrate", "-v0")
    compose(*as_practice, *nhanes, "prepare", *manage, "seed_practice", *seed)
    address = f"{APP_HOSPITAL}-messaging:8441"
    compose(*as_practice, "prepare", *manage, "add_laboratory", "AZ Diest", address)
    up(compose, practice)
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


@given("the SuperLink and UZ Leuven's SuperNode and ClientApp are running")
def flower_running(compose: Compose, flower: None) -> None:
    wait_until_online(compose)


@scenario("transmission.feature", "Train, transmit, transmit again")
def test_train_transmit_transmit_again() -> None:
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


@when(parsers.re("the data scientist transmits (that final model|it again)"))
def transmit(compose: Compose, journey: dict[str, Any]) -> None:
    journey["before"] = folders(compose)["hospital"]
    journey["transmission"] = flower_run(
        compose, f"transmit-final-model='{journey['training']}'"
    )


@then(
    "the transmitting run completes and UZ Leuven stores the final model under"
    " the training run's ID"
)
def stored(compose: Compose, journey: dict[str, Any]) -> None:
    held = folders(compose)["hospital"]
    assert list(held) == [f"{journey['training']}.pt"], held


@then("that run completes too and UZ Leuven's copy is unchanged")
def unchanged(compose: Compose, journey: dict[str, Any]) -> None:
    assert folders(compose)["hospital"] == journey["before"]
