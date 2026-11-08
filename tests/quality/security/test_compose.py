"""The demo as compose.yaml declares it (demo/README.md): each party's services
see only their own party's folder and reach only their crossings.

Read through `docker compose config`, which also validates the file.
"""

import json
import os
import re
import subprocess
from functools import cache
from pathlib import Path
from typing import Any

import pytest
from django.utils.text import slugify

from ml.dataset import CYCLES

ROOT = Path(__file__).resolve().parents[3]
# Each practice sends to the hospital of the same cycle (demo/README.md).
STARTUP_SERVICES = {
    "flower-superlink",
    "flower-server-app",
    "train",
    "startup-web",
    "startup-messaging",
}
# Out-of-band setup (report, assumptions): nhanes-download, the one service
# that reaches the internet, sees no party's folder.
SETUP_SERVICES = {"nhanes-download"}
# What a reset keeps, on the host: the downloads and the extracts made from them.
HOST_FOLDERS = {"huggingface", "nhanes"}
# Between the browser and the parties, like the internet: it sees only names.
NETWORK_SERVICES = {"proxy"}


# Settings a person may put in .env; the tests read the file without them.
SETTINGS = ("DEMO_USER", "DEMO_HTTP_PORT")


@cache
def config(demo_user: str | None = None, **settings: str) -> dict[str, Any]:
    """The file as compose reads it, with only the given settings set."""
    environment = {k: v for k, v in os.environ.items() if k not in SETTINGS}
    if demo_user is not None:
        environment["DEMO_USER"] = demo_user
    environment.update(settings)
    result = subprocess.run(
        ["docker", "compose", "--profile", "*", "config", "--format", "json"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    parsed: dict[str, Any] = json.loads(result.stdout)
    return parsed


def service(name: str) -> dict[str, Any]:
    found: dict[str, Any] = config()["services"][name]
    return found


def pairs() -> list[tuple[str, str, str, int]]:
    """nhanes-download's --pair arguments, as compose.yaml writes them: each
    hospital with its NHANES cycle, its practice and the practice's patients."""
    command: list[str] = service("nhanes-download")["command"]
    return [
        (command[at + 1], command[at + 2], command[at + 3], int(command[at + 4]))
        for at, part in enumerate(command)
        if part == "--pair"
    ]


def name(slug: str) -> str:
    """A practice's or hospital's name, as its web app shows it and calls as."""
    environment = service(f"{slug}-web")["environment"]
    found: str = environment.get("PRACTICE_NAME") or environment["HOSPITAL_NAME"]
    return found


HOSPITAL_SLUGS = [hospital for _, hospital, _, _ in pairs()]
PRACTICE_SLUGS = [practice for _, _, practice, _ in pairs()]


def test_the_demo_pairs_exactly_the_hospitals_training_knows() -> None:
    """Each hospital trains on its NHANES cycle (ml.dataset.CYCLES). Pass: compose
    names each cycle once, in that order, each with a hospital and a practice
    whose web apps run."""
    assert [cycle for cycle, _, _, _ in pairs()] == list(CYCLES)
    for slug in HOSPITAL_SLUGS + PRACTICE_SLUGS:
        assert f"{slug}-web" in config()["services"], slug


def volume_folder(volume: str) -> str:
    """The party a named volume belongs to, as a folder name."""
    if volume == "startup":
        return "startup"
    if volume in HOSPITAL_SLUGS:
        return f"hospitals/{volume}"
    if volume in PRACTICE_SLUGS:
        return f"practices/{volume}"
    raise AssertionError(f"{volume} is no party's volume")


def mounts(name: str) -> dict[str, tuple[str, bool]]:
    """Each mount's target, with what it shows and whether read-only: a party
    volume's folder and subpath, or bind:<path in the checkout> for the host."""
    found = {}
    for volume in service(name).get("volumes", []):
        if volume["type"] == "volume":
            subpath = volume.get("volume", {}).get("subpath")
            source = volume_folder(volume["source"])
            source += f"/{subpath}" if subpath else ""
        else:
            source = f"bind:{Path(volume['source']).relative_to(ROOT)}"
        found[volume["target"]] = (source, bool(volume.get("read_only", False)))
    return found


def party_folder(name: str) -> str:
    """The folder under .demo/ of the party a service belongs to."""
    if name in STARTUP_SERVICES:
        return "startup"
    for slug in HOSPITAL_SLUGS:
        if name.startswith(f"{slug}-"):
            return f"hospitals/{slug}"
    for slug in PRACTICE_SLUGS:
        if name.startswith(f"{slug}-"):
            return f"practices/{slug}"
    raise AssertionError(f"{name} belongs to no party")


def test_every_web_app_names_its_party_and_its_folder() -> None:
    """A web app without DATA_DIR would keep its data in the image's checkout
    (.data/<party>/), outside its party's volume. Pass: every service that runs
    a party's settings names them and a DATA_DIR."""
    web_apps = {
        name: spec["environment"]
        for name, spec in config()["services"].items()
        if "DJANGO_SETTINGS_MODULE" in (spec.get("environment") or {})
    }
    assert web_apps
    for name, environment in web_apps.items():
        assert environment["DJANGO_SETTINGS_MODULE"].endswith(".settings"), name
        # The folder the party's image brings (demo/party.py).
        assert environment.get("DATA_DIR") == "/data", name


def test_one_service_per_process_of_each_party() -> None:
    assert set(config()["services"]) == STARTUP_SERVICES | NETWORK_SERVICES | {
        "nhanes-download"
    } | {
        f"{slug}-{role}"
        for slug in HOSPITAL_SLUGS
        for role in ("flower-supernode", "flower-client-app", "web", "messaging")
    } | {f"{slug}-web" for slug in PRACTICE_SLUGS}


def test_each_service_mounts_only_its_own_partys_folder() -> None:
    parties = ["startup"] + [volume_folder(slug) for slug in HOSPITAL_SLUGS]
    parties += [volume_folder(slug) for slug in PRACTICE_SLUGS]
    # The public NHANES data only: no party's folder.
    assert mounts("nhanes-download") == {
        f"/demo/{name}": (f"bind:.demo/{name}", False) for name in HOST_FOLDERS
    }
    seen = set()
    for name in set(config()["services"]) - SETUP_SERVICES - NETWORK_SERVICES:
        folder = party_folder(name)
        for source, read_only in mounts(name).values():
            if source.startswith("bind:"):
                # Its own NHANES extract, read-only: no other party's.
                assert source == f"bind:.demo/nhanes/{folder.split('/')[-1]}", name
                assert read_only, name
            else:
                # Its own party's volume: `down -v` leaves no party data.
                assert source.startswith(folder), (name, source)
                seen.add(folder)
    assert seen == set(parties)


@pytest.mark.parametrize("slug", HOSPITAL_SLUGS)
def test_the_hospitals_web_app_writes_the_cohort_and_its_screening_models(
    slug: str,
) -> None:
    """The laboratory director provides the training cohort from the web app
    (features/hospital/training_cohort.feature) and fetches screening models there,
    validated on it (features/hospital/fetch.feature): the web app writes the
    cohort folder and screening-models, through the hospital's whole volume,
    unmasked, and the startup's code writes nothing at the hospital."""
    name = f"{slug}-web"
    assert "tmpfs" not in service(name)
    assert mounts(name) == {
        "/data": (f"hospitals/{slug}", False),
        "/nhanes": (f"bind:.demo/nhanes/{slug}", True),
    }


@pytest.mark.parametrize("slug", HOSPITAL_SLUGS)
def test_the_supernode_mounts_no_data(slug: str) -> None:
    assert mounts(f"{slug}-flower-supernode") == {}


@pytest.mark.parametrize(("http_port", "published"), [(None, "80"), ("8080", "8080")])
def test_only_the_proxy_is_published_and_only_on_localhost(
    http_port: str | None, published: str
) -> None:
    environment = {} if http_port is None else {"DEMO_HTTP_PORT": http_port}
    ports = {
        (name, port["host_ip"], port["published"])
        for name, spec in config(**environment)["services"].items()
        for port in spec.get("ports", [])
    }
    assert ports == {("proxy", "127.0.0.1", published)}


def test_the_proxy_reaches_every_web_app_and_nothing_else() -> None:
    assert set(service("proxy")["networks"]) == {
        "startup-web",
        *HOSPITAL_SLUGS,
        *PRACTICE_SLUGS,
    }


def test_the_startups_web_app_reaches_the_superlink_and_the_proxy_never_does() -> None:
    assert set(service("startup-web")["networks"]) == {"startup", "startup-web"}
    members = {
        name
        for name, spec in config()["services"].items()
        if "startup-web" in spec.get("networks", {})
    }
    assert members == {"startup-web", "proxy"}


def test_the_startups_web_app_reads_the_final_models_and_not_the_superlinks_state() -> (
    None
):
    spec = service("startup-web")
    assert set(spec["tmpfs"]) == {"/data/superlink"}
    assert mounts("startup-web")["/data/final-models"] == ("startup/final-models", True)
    assert spec["environment"]["DJANGO_SETTINGS_MODULE"] == "web.startup.settings"
    assert spec["environment"]["DATA_DIR"] == "/data"


@pytest.mark.parametrize("slug", ["startup", *HOSPITAL_SLUGS, *PRACTICE_SLUGS])
def test_the_proxy_routes_each_partys_name_to_its_web_app(slug: str) -> None:
    # Routing by the Host header: plain HTTP, the report's TLS left out. One
    # rule, <party>.localhost to <party>-web, so the proxy lists no party.
    conf = (ROOT / "demo" / "proxy.conf").read_text()
    (pattern,) = re.findall(r"server_name ~(\S+);", conf)
    (upstream,) = re.findall(r"proxy_pass http://(\S+);", conf)
    # nginx writes a named group (?<name>…), Python (?P<name>…).
    found = re.fullmatch(pattern.replace("(?<", "(?P<"), f"{slug}.localhost")
    assert found is not None, pattern
    assert upstream.replace("$party", found["party"]) == f"{slug}-web:8000"


def test_crossings_and_the_startup_are_internal_networks() -> None:
    networks = config()["networks"]
    internal = {name for name, spec in networks.items() if spec.get("internal")}
    assert internal == {"startup", "model-updates", "messaging", "screening-models"} | {
        f"{slug}-flower-client-app" for slug in HOSPITAL_SLUGS
    }


def test_model_updates_connect_only_the_superlink_and_the_supernodes() -> None:
    members = {
        name
        for name, spec in config()["services"].items()
        if "model-updates" in spec.get("networks", {})
    }
    assert members == {"flower-superlink"} | {
        f"{slug}-flower-supernode" for slug in HOSPITAL_SLUGS
    }


@pytest.mark.parametrize("practice", PRACTICE_SLUGS)
def test_each_practice_reaches_every_hospitals_lab_order_endpoint_and_nothing_else(
    practice: str,
) -> None:
    """A practice chooses the laboratory per sample (features/practice/ordering.feature); its laboratories are
    rows add_laboratory made, not environment variables."""
    spec = service(f"{practice}-web")
    assert set(spec["networks"]) == {practice, "messaging"}
    assert "MESSAGING_ADDRESS" not in spec["environment"]


def test_one_messaging_network_holds_every_hospital_and_practice_only() -> None:
    """Every practice may send to every hospital (features/practice/ordering.feature): one crossing, TB3-TB1,
    like the internet between them; separate networks would isolate nothing."""
    members = {
        name
        for name, spec in config()["services"].items()
        if "messaging" in spec.get("networks", {})
    }
    assert members == {f"{slug}-messaging" for slug in HOSPITAL_SLUGS} | {
        f"{slug}-web" for slug in PRACTICE_SLUGS
    }


@pytest.mark.parametrize("slug", HOSPITAL_SLUGS)
def test_the_hospital_serves_its_pages_and_its_messaging_from_containers_of_their_own(
    slug: str,
) -> None:
    # One container per server, each on one network: its practices reach the
    # lab-order endpoint and never the pages.
    web, messaging = service(f"{slug}-web"), service(f"{slug}-messaging")
    # screening-models: to fetch screening models from the startup; it serves
    # nothing there.
    assert set(web["networks"]) == {slug, "screening-models"}
    assert set(messaging["networks"]) == {"messaging"}
    assert "--bind=0.0.0.0:8000" in web["command"]
    assert messaging["command"][-2:] == ["serve_messages", "0.0.0.0:8441"]
    # Only the web app sets the party up (demo/party.py); the endpoint waits for it.
    assert messaging["entrypoint"] == []
    assert messaging["depends_on"][f"{slug}-web"]["condition"] == "service_healthy"
    assert mounts(f"{slug}-messaging") == {"/data": (f"hospitals/{slug}", False)}


def test_each_web_app_knows_its_name_and_primary_colour() -> None:
    vendor = ROOT / "web/shared/static/css/vendor/pico-2.1.1"
    for slug in HOSPITAL_SLUGS + PRACTICE_SLUGS:
        environment = service(f"{slug}-web")["environment"]
        assert name(slug), slug
        colour = environment["PRIMARY_COLOUR"]
        assert (vendor / f"pico.{colour}.min.css").is_file(), (slug, colour)


def test_no_practice_service_runs_on_a_timer() -> None:
    # Lab reports come only on Check for reports (tests/practice/test_messaging.py).
    for name, spec in config()["services"].items():
        assert "REPORT_CHECK_SECONDS" not in (spec.get("environment") or {}), name


def test_the_superlink_keeps_its_state_with_the_startup() -> None:
    assert (
        "--database=/demo/startup/superlink/state.db"
        in service("flower-superlink")["command"]
    )
    assert mounts("flower-superlink")["/demo/startup/superlink"] == (
        "startup/superlink",
        False,
    )


def test_down_v_deletes_every_partys_data_and_keeps_the_host_folders() -> None:
    # One volume per party, none external, so `docker compose down -v` deletes
    # them all; the downloads stay on the host.
    volumes = config()["volumes"]
    assert set(volumes) == {"startup", *HOSPITAL_SLUGS, *PRACTICE_SLUGS}
    assert not any(spec.get("external") for spec in volumes.values())
    binds = {
        (name, source)
        for name in config()["services"]
        for source, _ in mounts(name).values()
        if source.startswith("bind:")
    }
    extracts = {
        (f"{slug}-web", f"bind:.demo/nhanes/{slug}")
        for slug in HOSPITAL_SLUGS + PRACTICE_SLUGS
    }
    assert binds == {
        ("nhanes-download", f"bind:.demo/{name}") for name in HOST_FOLDERS
    } | extracts | {("proxy", "bind:demo/proxy.conf")}
    assert service("nhanes-download")["environment"]["HF_HOME"] == "/demo/huggingface"


def test_only_nhanes_download_reaches_the_internet() -> None:
    """Threat: a party's data leaving through a container that reaches the
    internet. Pass: nhanes-download, which sees no party's folder, is the only
    service on the one network that is not internal."""
    networks = config()["networks"]
    outside = {name for name, spec in networks.items() if not spec.get("internal")}
    on_outside = {
        name
        for name, spec in config()["services"].items()
        if outside & set(spec.get("networks") or {})
    }
    assert "setup" in outside
    reaching = {
        name for name in on_outside if "setup" in config()["services"][name]["networks"]
    }
    assert reaching == {"nhanes-download"}


@pytest.mark.parametrize(
    ("demo_user", "user"), [(None, "1000:1000"), ("1234:5678", "1234:5678")]
)
def test_every_service_runs_as_the_demo_user(demo_user: str | None, user: str) -> None:
    # Every container that touches a party's volume runs as our images' app
    # user, who owns the folders each image brings into a fresh volume: none
    # needs root. Only nhanes-download writes to the host, where on Linux a bind
    # mount keeps numeric IDs: it starts as root, to hand .demo/ to DEMO_USER.
    services = config(demo_user)["services"]
    users = {
        spec.get("user")
        for name, spec in services.items()
        if name not in SETUP_SERVICES
    }
    assert users == {"1000:1000"}
    download = services["nhanes-download"]
    # .demo/'s folders are in the checkout, the cloner's: nothing hands them over.
    assert download["user"] == user
    assert download.get("entrypoint") is None
    for folder in HOST_FOLDERS:
        assert (ROOT / ".demo" / folder / ".gitkeep").is_file(), folder


@pytest.mark.parametrize(
    "name",
    [f"{slug}-web" for slug in ["startup", *HOSPITAL_SLUGS, *PRACTICE_SLUGS]]
    + ["proxy"],
)
def test_what_others_wait_for_says_when_it_is_ready(name: str) -> None:
    # Compose, and the container tests (`up --wait`), wait on health, not a clock.
    assert service(name)["healthcheck"]["test"][0] == "CMD", name


@pytest.mark.parametrize(
    ("name", "port"),
    [(f"{slug}-messaging", 8441) for slug in HOSPITAL_SLUGS]
    + [("startup-messaging", 8442), ("flower-superlink", 9092)]
    + [(f"{slug}-flower-supernode", 9094) for slug in HOSPITAL_SLUGS],
)
def test_a_server_without_pages_is_ready_when_its_port_answers(
    name: str, port: int
) -> None:
    check = " ".join(service(name)["healthcheck"]["test"])
    assert f"('localhost', {port})" in check, name


@pytest.mark.parametrize("slug", HOSPITAL_SLUGS)
def test_the_clientapp_waits_for_its_supernode_to_answer(slug: str) -> None:
    waits = service(f"{slug}-flower-client-app")["depends_on"]
    assert waits[f"{slug}-flower-supernode"]["condition"] == "service_healthy"


def test_the_proxy_waits_for_every_web_app_to_answer() -> None:
    waits = service("proxy")["depends_on"]
    assert waits == {
        f"{slug}-web": waits[f"{slug}-web"]
        for slug in ["startup", *HOSPITAL_SLUGS, *PRACTICE_SLUGS]
    }
    assert {wait["condition"] for wait in waits.values()} == {"service_healthy"}


def test_every_long_running_service_restarts() -> None:
    # A crash stays down only for the two that must exit.
    for name, spec in config()["services"].items():
        expected = None if name in {"nhanes-download", "train"} else "unless-stopped"
        assert spec.get("restart") == expected, name


@pytest.mark.parametrize(
    "name", [f"{slug}-web" for slug in ["startup", *HOSPITAL_SLUGS, *PRACTICE_SLUGS]]
)
def test_a_web_app_is_ready_when_its_login_page_answers(name: str) -> None:
    # An open port says nothing of Django: the login page needs its settings,
    # URLconf, templates and stylesheet manifest, and urlopen fails on 4xx and 5xx.
    check = " ".join(service(name)["healthcheck"]["test"])
    assert "urllib.request.urlopen(" in check, name
    assert ":8000/login/'" in check, name


def test_each_project_runs_images_of_its_own() -> None:
    # Shared tags let another worktree's or test run's build replace the images
    # a running project uses between its build and its `up`.
    result = subprocess.run(
        ["docker", "compose", "-p", "some-project", "config", "--format", "json"],
        cwd=ROOT / "demo",
        capture_output=True,
        text=True,
        check=True,
    )
    built = {
        spec["image"]
        for spec in json.loads(result.stdout)["services"].values()
        if not spec["image"].startswith(("flwr/", "nginx:"))
    }
    assert built == {
        "some-project-nhanes-download",
        "some-project-hospital-web",
        "some-project-startup-web",
        "some-project-practice-web",
        "some-project-superexec",
    }


def test_every_flower_connection_runs_without_tls() -> None:
    """The demo admits any SuperNode: a gap, pinned so it is not mistaken for the
    report's control (the SuperLink admits only the SuperNodes whose public key
    the startup registered, over TLS). Pass: every Flower component runs with
    --insecure, and nothing else does."""
    insecure = {
        name
        for name, spec in config()["services"].items()
        if "--insecure" in (spec.get("command") or [])
    }
    assert insecure == {"flower-superlink", "flower-server-app"} | {
        f"{slug}-flower-{role}"
        for slug in HOSPITAL_SLUGS
        for role in ("supernode", "client-app")
    }


@pytest.mark.parametrize("slug", HOSPITAL_SLUGS)
def test_compose_gives_the_startups_code_only_the_cohort_read_only(
    slug: str,
) -> None:
    """The ClientApp, the startup's code at each hospital (DF7, TB4), sees no
    database, no key and no other party's folder, so what it sends leaves only
    through DF9 and DF10, and it writes nothing at the hospital: a screening model
    enters only when the hospital fetches it (features/hospital/fetch.feature).
    Pass: it mounts only its hospital's cohort, read-only, and shares one
    internal network only with its hospital's SuperNode."""
    declared = config()
    clientapp = f"{slug}-flower-client-app"
    assert mounts(clientapp) == {
        f"/demo/hospitals/{slug}/cohort": (f"hospitals/{slug}/cohort", True),
    }
    assert set(service(clientapp)["networks"]) == {clientapp}
    assert declared["networks"][clientapp]["internal"] is True
    members = {
        name
        for name, spec in declared["services"].items()
        if clientapp in spec.get("networks", {})
    }
    assert members == {clientapp, f"{slug}-flower-supernode"}


def test_no_running_service_has_debug_on() -> None:
    """Every web app runs gunicorn with DEBUG off; only the seed commands that
    prepare runs set DJANGO_DEBUG, for themselves. Pass: no service sets
    DJANGO_DEBUG."""
    with_debug = {
        name
        for name, spec in config()["services"].items()
        if "DJANGO_DEBUG" in (spec.get("environment") or {})
    }
    assert with_debug == set()


def test_the_startups_web_server_outwaits_a_submission() -> None:
    # A request that outlives gunicorn's worker timeout ends without the page
    # saying why; the submission gives up first.
    from web.startup.training.runs import SUBMIT_TIMEOUT_SECONDS

    command = service("startup-web")["command"]
    timeouts = [
        int(arg.split("=")[1]) for arg in command if arg.startswith("--timeout=")
    ]
    assert (timeouts or [30])[0] > SUBMIT_TIMEOUT_SECONDS  # gunicorn's default: 30


def test_a_health_check_runs_often_only_while_its_service_starts() -> None:
    # Each check starts a process in the container: every 2 s until the service
    # is up, so `up --wait` is quick, then rarely.
    checks = {
        name: spec["healthcheck"]
        for name, spec in config()["services"].items()
        if "healthcheck" in spec
    }
    assert len(checks) == 9 + 4 + 3
    for name, check in checks.items():
        assert (check["start_interval"], check["interval"]) == ("2s", "5m0s"), name


def test_only_the_hospitals_web_apps_reach_the_startups_messaging_endpoint() -> None:
    """The startup's messaging endpoint (P5) serves recipient hospitals only
    (features/startup/release.feature). Pass: the screening-models network joins the
    startup's web app and every hospital's web app, nothing else, and is internal."""
    declared = config()
    members = {
        name
        for name, spec in declared["services"].items()
        if "screening-models" in spec.get("networks", {})
    }
    assert members == {"startup-messaging"} | {f"{slug}-web" for slug in HOSPITAL_SLUGS}
    assert declared["networks"]["screening-models"]["internal"] is True


def test_the_startup_serves_its_pages_and_its_screening_models_from_containers_of_their_own() -> (
    None
):
    # The proxy reaches the pages, the hospitals' web apps only the
    # messaging endpoint (features/startup/release.feature).
    web, endpoint = service("startup-web"), service("startup-messaging")
    assert set(endpoint["networks"]) == {"screening-models"}
    assert "--bind=0.0.0.0:8000" in web["command"]
    assert endpoint["command"][-2:] == ["serve_messages", "0.0.0.0:8442"]
    assert endpoint["entrypoint"] == []
    assert endpoint["depends_on"]["startup-web"]["condition"] == "service_healthy"
    # Like the web app: the final models read-only, the SuperLink's state masked.
    assert mounts("startup-messaging") == mounts("startup-web")
    assert endpoint["tmpfs"] == web["tmpfs"]


@pytest.mark.parametrize("slug", HOSPITAL_SLUGS)
def test_each_hospital_fetches_from_the_startup_by_its_name(slug: str) -> None:
    environment = service(f"{slug}-web")["environment"]
    assert environment["STARTUP_ADDRESS"] == "startup-messaging:8442"
    # What it calls the startup as: its name's slug, its folder name.
    assert slugify(environment["HOSPITAL_NAME"]) == slug


def registered(name: str) -> list[list[str]]:
    from demo.party import registrations

    return registrations(service(name)["environment"].get("DEMO_REGISTER", ""))


@pytest.mark.parametrize("slug", HOSPITAL_SLUGS)
def test_every_hospital_knows_every_practice_by_its_name(slug: str) -> None:
    """Any practice may send a sample to any hospital
    (features/practice/ordering.feature), so each hospital registers every
    practice, by the name its app calls as, whose slug is its folder name."""
    assert registered(f"{slug}-web") == [
        ["add_practice", name(practice)] for practice in PRACTICE_SLUGS
    ]
    assert [slugify(name(practice)) for practice in PRACTICE_SLUGS] == PRACTICE_SLUGS


def test_the_startup_knows_every_hospital_by_the_name_its_web_app_calls_as() -> None:
    """Any hospital may fetch released final models as screening models
    (features/startup/release.feature), so the startup registers every one, by
    the name its web app calls as."""
    assert registered("startup-web") == [
        ["add_hospital", name(hospital)] for hospital in HOSPITAL_SLUGS
    ]


@pytest.mark.parametrize(("paired", "practice"), [(h, p) for _, h, p, _ in pairs()])
def test_each_practice_sends_to_its_own_hospital_unless_told_otherwise(
    paired: str, practice: str
) -> None:
    """Every hospital's laboratory, its paired hospital's the primary one, so lab
    orders follow the hospitals' sizes by default."""
    commands = registered(f"{practice}-web")
    assert [command[1] for command in commands] == [name(h) for h in HOSPITAL_SLUGS]
    for command, hospital in zip(commands, HOSPITAL_SLUGS, strict=True):
        assert command[2] == f"{hospital}-messaging:8441"
        assert ("--primary" in command) is (hospital == paired)


def test_two_hospitals_provide_their_training_cohort_at_start() -> None:
    """AZ Diest's laboratory director has not, so a training run shows a hospital
    taking no part until its director provides one."""
    provides = {
        slug: service(f"{slug}-web")["environment"].get("DEMO_PROVIDE") == "1"
        for slug in HOSPITAL_SLUGS
    }
    assert provides == {
        "uz-leuven": True,
        "heilig-hart-leuven": True,
        "az-diest": False,
    }
