"""The running containers keep the trust boundaries, as Docker runs compose.yaml:
the startup's code at a hospital, the networks between the parties, and the
web apps with DEBUG off. Every test here needs a Docker engine and starts only
the services it asks for (tests/compose_project.py). Each test's docstring
states its pass/fail measure."""

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.compose_project import (
    APP_HOSPITAL,
    APP_PRACTICE,
    HOSPITAL,
    PROJECT,
    ROOT,
    Compose,
    build,
    flwr,
    probe,
    wait_until_online,
)

pytestmark = pytest.mark.containers


def test_the_startups_running_code_finds_only_the_cohort_and_reaches_nothing(
    compose: Compose, flower: None, tmp_path: Path
) -> None:
    """The ClientApp, the startup's code at UZ Leuven, runs in a container that
    mounts only the cohort and the screening models, on a network it shares
    only with the SuperNode; UZ Leuven's folder holds a database beside the
    cohort (the flower fixture), for it to miss. Pass: an app the data
    scientist runs finds, at every hospital whose ClientApp runs, only that
    hospital's cohort and screening models, and reaches no address."""
    wait_until_online(compose)
    copy = tmp_path / "probe"
    shutil.copytree(ROOT / "tests" / "quality" / "security" / "probe", copy)
    output = flwr(
        compose,
        "-v",
        f"{copy}:/probe",
        "train",
        "flwr",
        "run",
        "/probe",
        "demo",
        "--stream",
    )
    reports: list[dict[str, Any]] = [
        json.loads(line.split("PROBE ", 1)[1])
        for line in output.splitlines()
        if "PROBE {" in line
    ]
    # Every hospital whose ClientApp runs now answers; UZ Leuven always does.
    assert HOSPITAL in {report["hospital"] for report in reports}, reports
    for report in reports:
        own = tuple(
            f"/demo/hospitals/{report['hospital']}/{folder}/"
            for folder in ("cohort", "screening-models")
        )
        assert report["files"], report
        assert all(path.startswith(own) for path in report["files"]), report
        assert report["reachable"] == [], report


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


def test_a_hospitals_web_app_serves_its_pages_and_stylesheets(
    compose: Compose, hospital_app: str
) -> None:
    """AZ Diest's web app runs gunicorn with DEBUG off, and WhiteNoise serves its
    stylesheets. Pass: its login page and that page's stylesheet both answer
    200, the stylesheet as text/css."""
    fetched: dict[str, Any] = probe(
        compose, hospital_app, FETCH, f"{APP_HOSPITAL}-pages"
    )
    assert fetched["login"] == 200, fetched
    # On a failure, which stylesheet it asked for and the page it got.
    assert fetched["css"][0] == 200, fetched
    assert fetched["css"][1].startswith("text/css"), fetched


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


def test_a_practice_reaches_the_hospitals_lab_order_endpoint_and_not_its_pages(
    compose: Compose, hospital_app: str
) -> None:
    """One container serves AZ Diest's pages (8000) and its lab-order endpoint
    (8441, DF23, DF25), each under a name only one network knows. Pass: from
    practice De Ceder's web app, on the messaging network, only 8441
    answers."""
    build(compose, "practice-web")
    answers = probe(
        compose,
        f"{APP_PRACTICE}-web",
        PORTS,
        f"{APP_HOSPITAL}-messaging",
        "8441",
        "8000",
    )
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


def test_the_proxy_hands_a_browser_only_the_party_it_names(
    compose: Compose, hospital_app: str, proxy: None
) -> None:
    """The proxy, the only published port, routes each <party>.localhost by its
    Host header. Pass: az-diest.localhost gets AZ Diest's web app, and a name
    the proxy does not route (bank.example) gets the proxy's refusal, 421."""

    def ask(name: str) -> str:
        status: str = probe(compose, hospital_app, THROUGH_PROXY, "proxy", name)
        return status

    assert ask(f"{APP_HOSPITAL}.localhost") == "200"
    # The proxy's own refusal, before any web app could answer.
    assert ask("bank.example") == "421"


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


def test_the_startups_web_app_reaches_the_superlink_and_not_its_state(
    compose: Compose, superlink: None
) -> None:
    """The startup's web app submits training runs to the SuperLink; the
    SuperLink's state is the SuperLink's alone. Pass: from the web app's
    container the SuperLink answers and its state folder is empty."""
    sight = probe(compose, "startup-web", STARTUP_SIGHT)
    expected = {"superlink": "open", "state": []}
    # This test has failed now and then with no trace of why: when it fails,
    # say what the SuperLink was doing.
    evidence = (
        ""
        if sight == expected
        else compose("ps", "--all").stdout
        + compose("logs", "--tail", "40", "flower-superlink").stdout
    )
    assert sight == expected, evidence


# The parties whose web apps no test here starts: their own networks must not exist.
NOT_UNDER_TEST = {
    HOSPITAL,
    "heilig-hart-leuven",
    "huisartsenpraktijk-de-akker",
    "huisartsenpraktijk-de-berk",
}


def test_the_project_creates_no_network_of_a_party_not_under_test(
    compose: Compose, proxy: None
) -> None:
    """The project holds only the networks of what runs, so it shares Docker's
    address pool with a running demo. Pass: the networks of AZ Diest and De
    Ceder exist, and none of a party whose web app no test starts."""
    project = PROJECT[compose]
    listing = subprocess.run(
        ["docker", "network", "ls", "--format", "{{.Name}}", "--filter"]
        + [f"label=com.docker.compose.project={project}"],
        capture_output=True,
        text=True,
        check=True,
    )
    networks = {name.removeprefix(f"{project}_") for name in listing.stdout.split()}
    assert {APP_HOSPITAL, APP_PRACTICE} <= networks, networks
    assert networks.isdisjoint(NOT_UNDER_TEST), networks
