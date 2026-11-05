"""The demo deployment as compose.yaml declares it (spec §9, R21, R28).

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

from demo.topology import COLOURS, PRACTICES
from iron_deficiency.dataset import CYCLES, HOSPITALS, hospital_slug

ROOT = Path(__file__).resolve().parents[2]
HOSPITAL_SLUGS = [hospital_slug(HOSPITALS[cycle]) for cycle in CYCLES]
PRACTICE_SLUGS = [hospital_slug(PRACTICES[cycle]) for cycle in CYCLES]
# Each practice sends to the hospital of the same cycle (spec §9).
STARTUP_SERVICES = {
    "prepare",
    "flower-superlink",
    "flower-server-app",
    "train",
}
# Out-of-band setup (report, assumptions): the one service that sees every party.
SETUP_SERVICES = {"prepare"}
# What a reset keeps, on the host: the downloads.
HOST_FOLDERS = {"huggingface"}
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


def volume_folder(volume: str) -> str:
    """The party folder a named volume holds, as prepare lays it out under /demo."""
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


def test_one_service_per_process_of_each_party() -> None:
    assert set(config()["services"]) == STARTUP_SERVICES | NETWORK_SERVICES | {
        f"{slug}-{role}"
        for slug in HOSPITAL_SLUGS
        for role in ("flower-supernode", "flower-client-app", "web")
    } | {f"{slug}-web" for slug in PRACTICE_SLUGS}


def test_each_service_mounts_only_its_own_partys_folder() -> None:
    parties = ["startup"] + [volume_folder(slug) for slug in HOSPITAL_SLUGS]
    parties += [volume_folder(slug) for slug in PRACTICE_SLUGS]
    assert mounts("prepare") == {
        **{f"/demo/{folder}": (folder, False) for folder in parties},
        **{f"/demo/{name}": (f"bind:.demo/{name}", False) for name in HOST_FOLDERS},
    }
    for name in set(config()["services"]) - SETUP_SERVICES - NETWORK_SERVICES:
        folder = party_folder(name)
        for target, (source, _) in mounts(name).items():
            # A party volume, never the host: `down -v` leaves no party data.
            assert source.startswith(folder), (name, source)
            # Every container sees a folder at the path prepare wrote it to.
            assert target == f"/demo/{source}", (name, target)


@pytest.mark.parametrize("slug", HOSPITAL_SLUGS)
def test_the_startups_code_at_a_hospital_sees_only_the_cohort_and_final_models(
    slug: str,
) -> None:
    clientapp = f"{slug}-flower-client-app"
    assert mounts(clientapp) == {
        f"/demo/hospitals/{slug}/cohort": (f"hospitals/{slug}/cohort", True),
        f"/demo/hospitals/{slug}/final-models": (
            f"hospitals/{slug}/final-models",
            False,
        ),
    }
    # It reaches its SuperNode and nothing else: no web app, no internet.
    assert set(service(clientapp)["networks"]) == {f"{slug}-flower-client-app"}
    assert config()["networks"][f"{slug}-flower-client-app"]["internal"] is True
    members = {
        name
        for name, spec in config()["services"].items()
        if f"{slug}-flower-client-app" in spec.get("networks", {})
    }
    assert members == {clientapp, f"{slug}-flower-supernode"}


@pytest.mark.parametrize("slug", HOSPITAL_SLUGS)
def test_the_hospitals_own_apps_see_no_cohort_and_read_only_final_models(
    slug: str,
) -> None:
    name = f"{slug}-web"
    assert set(service(name)["tmpfs"]) == {f"/demo/hospitals/{slug}/cohort"}
    final_models = f"/demo/hospitals/{slug}/final-models"
    assert mounts(name)[final_models] == (f"hospitals/{slug}/final-models", True)


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
    assert set(service("proxy")["networks"]) == set(HOSPITAL_SLUGS + PRACTICE_SLUGS)


@pytest.mark.parametrize("slug", HOSPITAL_SLUGS + PRACTICE_SLUGS)
def test_the_proxy_routes_each_partys_name_to_its_web_app(slug: str) -> None:
    # Routing by the Host header: plain HTTP, the report's TLS left out.
    conf = (ROOT / "demo" / "proxy.conf").read_text()
    routes = dict(
        re.findall(r"^\s*([a-z-]+\.localhost)\s+([a-z-]+:\d+);", conf, re.MULTILINE)
    )
    assert routes[f"{slug}.localhost"] == f"{slug}-web:8000"


def test_crossings_and_the_startup_are_internal_networks() -> None:
    networks = config()["networks"]
    internal = {name for name, spec in networks.items() if spec.get("internal")}
    assert internal == {"startup", "model-updates", "lab-orders"} | {
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
    """A practice chooses the laboratory per sample (R22); its laboratories are
    rows add_laboratory made, not environment variables."""
    spec = service(f"{practice}-web")
    assert set(spec["networks"]) == {practice, "lab-orders"}
    assert "MESSAGING_ADDRESS" not in spec["environment"]


def test_one_lab_orders_network_holds_every_hospital_and_practice_only() -> None:
    """Every practice may send to every hospital (R22): one crossing, TB3-TB1,
    like the internet between them; separate networks would isolate nothing."""
    members = {
        name
        for name, spec in config()["services"].items()
        if "lab-orders" in spec.get("networks", {})
    }
    assert members == {f"{slug}-web" for slug in HOSPITAL_SLUGS + PRACTICE_SLUGS}


@pytest.mark.parametrize("slug", HOSPITAL_SLUGS)
def test_the_hospital_serves_its_pages_and_its_lab_orders_each_on_one_network_only(
    slug: str,
) -> None:
    # One container, two servers: each listens on a name only one network
    # knows, so its practice reaches port 8441 and never the pages on 8000.
    spec = service(f"{slug}-web")
    assert spec["networks"] == {
        slug: {"aliases": [f"{slug}-pages"]},
        "lab-orders": {"aliases": [f"{slug}-lab-orders"]},
    }
    script = spec["command"][-1]
    assert f"--bind={slug}-pages:8000" in script
    assert f"serve_messages {slug}-lab-orders:8441" in script
    # Either server stopping stops the container, which compose restarts.
    assert "wait -n" in script
    assert spec["restart"] == "unless-stopped"


def test_each_web_app_knows_its_party_name_and_colour() -> None:
    vendor = ROOT / "static/css/vendor/pico-2.1.1"
    for cycle, (hospital_colour, practice_colour) in COLOURS.items():
        hospital = service(f"{hospital_slug(HOSPITALS[cycle])}-web")["environment"]
        assert hospital["HOSPITAL_NAME"] == HOSPITALS[cycle]
        assert hospital["PARTY_COLOUR"] == hospital_colour
        practice = service(f"{hospital_slug(PRACTICES[cycle])}-web")["environment"]
        assert practice["PRACTICE_NAME"] == PRACTICES[cycle]
        assert practice["PARTY_COLOUR"] == practice_colour
        for colour in (hospital_colour, practice_colour):
            assert (vendor / f"pico.{colour}.min.css").is_file(), colour


def test_no_practice_service_runs_on_a_timer() -> None:
    # Lab reports come only on Check for reports (R23).
    for name, spec in config()["services"].items():
        assert "REPORT_CHECK_SECONDS" not in (spec.get("environment") or {}), name


def test_every_flower_connection_runs_without_tls() -> None:
    # The report's TLS and SuperNode authentication are left out of the demo.
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
    assert binds == {("prepare", f"bind:.demo/{name}") for name in HOST_FOLDERS} | {
        ("proxy", "bind:demo/proxy.conf")
    }
    assert service("prepare")["environment"]["HF_HOME"] == "/demo/huggingface"


def test_no_running_service_runs_with_debug() -> None:
    # Only prepare seeds the demo accounts, which needs DJANGO_DEBUG (R15).
    with_debug = {
        name
        for name, spec in config()["services"].items()
        if "DJANGO_DEBUG" in (spec.get("environment") or {})
    }
    assert with_debug == set()


@pytest.mark.parametrize(
    ("demo_user", "user"), [(None, "1000:1000"), ("1234:5678", "1234:5678")]
)
def test_every_service_runs_as_the_demo_user(demo_user: str | None, user: str) -> None:
    # A fresh volume belongs to root, and on Linux a bind mount keeps numeric
    # IDs: every container writes as one user, by default the first account of
    # most Linux machines. Only prepare starts as root, to hand them over.
    services = config(demo_user)["services"]
    users = {spec.get("user") for name, spec in services.items() if name != "prepare"}
    assert users == {user}
    prepare = services["prepare"]
    assert prepare["user"] == "root"
    assert prepare["environment"]["DEMO_USER"] == user
    script = prepare["entrypoint"][-2]
    assert "chown" in script
    assert "exec setpriv" in script


@pytest.mark.parametrize(
    "name",
    [f"{slug}-web" for slug in HOSPITAL_SLUGS + PRACTICE_SLUGS] + ["proxy"],
)
def test_what_others_wait_for_says_when_it_is_ready(name: str) -> None:
    # Compose, and the container tests (`up --wait`), wait on health, not a clock.
    assert service(name)["healthcheck"]["test"][0] == "CMD", name


@pytest.mark.parametrize("slug", HOSPITAL_SLUGS)
def test_a_hospital_is_ready_when_both_its_servers_answer(slug: str) -> None:
    check = " ".join(service(f"{slug}-web")["healthcheck"]["test"])
    assert f"('{slug}-pages', 8000)" in check
    assert f"('{slug}-lab-orders', 8441)" in check


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
        "some-project-web",
        "some-project-practice-web",
        "some-project-superexec",
    }
