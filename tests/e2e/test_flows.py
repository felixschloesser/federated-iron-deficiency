"""End to end through the running demo: a CBC from the practice to the laboratory
and back through the proxy, as a browser; and a final model trained through the
real Flower apps, released at the startup and fetched as a screening model by
the hospital's own web app, twice (features/screening_model_journey.feature).
Every test here needs a Docker engine (tests/e2e/conftest.py)."""

import json
import time
from typing import Any

import pytest
from pytest_bdd import given, parsers, scenario, then, when

from tests.compose_project import (
    APP_HOSPITAL,
    APP_PRACTICE,
    HOSPITAL,
    SECOND_HOSPITAL,
    Compose,
    build,
    flwr,
    in_party,
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
_, page = lab.post(analyse, to_analyse)
seen["analysed"] = "CBC analysed" in page

_, page = doctor.get(patient)
back, page = doctor.post(f"{patient}check-for-reports/", page)
seen["fetched"] = back == patient and "1 new lab report." in page
seen["released"] = "Lab report released" in page
print(json.dumps(seen))
"""


def test_a_cbc_goes_from_the_practice_to_the_laboratory_and_back(
    compose: Compose, hospital_app: str, proxy: None
) -> None:
    build(compose, "practice-web")
    from demo.seeding.accounts import PASSWORD

    # Each party sets itself up from its own NHANES extract, the same
    # participants at both (tests/compose_project.py), as in the demo.
    practice = f"{APP_PRACTICE}-web"
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


@scenario("screening_model_journey.feature", "Train, release, fetch, fetch again")
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


def held(folder: str) -> str:
    """Python printing the model files in `folder`: each file's name and SHA-256."""
    return (
        "import hashlib, json; from pathlib import Path;"
        " print(json.dumps({path.name: hashlib.sha256(path.read_bytes()).hexdigest()"
        f" for path in sorted(Path({folder!r}).glob('*.pt'))}}))"
    )


def folders(compose: Compose) -> dict[str, Any]:
    """What the startup and UZ Leuven hold, each seen in its own web app."""
    return {
        "startup": json.loads(
            in_party(compose, "startup-web", held("/data/final-models"))
        ),
        "hospital": json.loads(
            in_party(compose, f"{HOSPITAL}-web", held("/data/screening-models"))
        ),
    }


@pytest.fixture
def journey() -> dict[str, Any]:
    return {}


@given(
    "Heilig Hart Leuven's SuperNode and ClientApp too, as FedAvg trains only with"
    " two hospitals"
)
def second_hospital(compose: Compose) -> None:
    up(compose, f"{SECOND_HOSPITAL}-web")
    cohort = "from pathlib import Path" + synthetic_cohort(SECOND_HOSPITAL)
    in_party(compose, f"{SECOND_HOSPITAL}-web", cohort)
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


# The startup's web app set itself up as it started: its data scientist, and
# every hospital a recipient by its folder's name. AZ Diest never trained here:
# any hospital the startup registers may fetch.
RELEASE = """
from django.utils import timezone
from web.shared.accounts.models import User
from web.startup.training.models import Release
Release.objects.release(
    final_model_run_id={run_id!r},
    released_by=User.objects.get(username="data-scientist"),
    now=timezone.now(),
)
"""

# What the laboratory director's Fetch new screening models runs, in AZ Diest's
# own web app container, on the screening-models network; the run IDs it stored.
FETCH_SCREENING_MODELS = """
import json
from django.utils import timezone
from web.hospital.deployment.fetching import fetch_screening_models
print(json.dumps(fetch_screening_models(now=timezone.now())))
"""


def stored_at(compose: Compose, hospital: str) -> dict[str, str]:
    """The screening models a hospital stored: each file's name and SHA-256."""
    stored: dict[str, str] = json.loads(
        in_party(compose, f"{hospital}-web", held("/data/screening-models"))
    )
    return stored


@when("the data scientist releases that final model")
def release(compose: Compose, journey: dict[str, Any]) -> None:
    release_one = RELEASE.format(run_id=journey["training"])
    compose(
        "exec", "-T", "startup-web", "python", "manage.py", "shell", "-c", release_one
    )
    # AZ Diest's own cohort, to validate on, in its own web app.
    up(compose, f"{APP_HOSPITAL}-web")
    cohort = "from pathlib import Path" + synthetic_cohort(APP_HOSPITAL)
    in_party(compose, f"{APP_HOSPITAL}-web", cohort)


@then("AZ Diest stores none yet")
def none_yet(compose: Compose) -> None:
    assert stored_at(compose, APP_HOSPITAL) == {}


@when(parsers.re("AZ Diest fetches new screening models(?: again)?"))
def hospital_fetches(compose: Compose, journey: dict[str, Any]) -> None:
    journey["before"] = stored_at(compose, APP_HOSPITAL)
    result = compose(
        "exec",
        "-T",
        f"{APP_HOSPITAL}-web",
        "python",
        "manage.py",
        "shell",
        "-c",
        FETCH_SCREENING_MODELS,
    )
    journey["fetched"] = json.loads(result.stdout.strip().splitlines()[-1])


@then(
    "AZ Diest stores the screening model under the training run's ID, with its local"
    " validation"
)
def stored(compose: Compose, journey: dict[str, Any]) -> None:
    assert journey["fetched"] == [int(journey["training"])]
    held = stored_at(compose, APP_HOSPITAL)
    assert list(held) == [f"{journey['training']}.pt"], held
    path = f"/data/screening-models/{journey['training']}.pt"
    script = (
        "from pathlib import Path;"
        " from web.hospital.deployment.model_files import read_screening_model;"
        f" model = read_screening_model(Path({path!r}).read_bytes());"
        " print(model is not None)"
    )
    assert in_party(compose, f"{APP_HOSPITAL}-web", script) == "True"


@then("it fetches none and AZ Diest's copy is unchanged")
def unchanged(compose: Compose, journey: dict[str, Any]) -> None:
    assert journey["fetched"] == []
    assert stored_at(compose, APP_HOSPITAL) == journey["before"]
