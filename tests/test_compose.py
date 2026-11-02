"""The demo deployment as compose.yaml declares it (spec §9, R21, R27, R28).

Read through `docker compose config`, which also validates the file.
"""

import json
import os
import subprocess
from functools import cache
from pathlib import Path
from typing import Any

import pytest

from iron_deficiency.dataset import CYCLES, HOSPITALS, hospital_slug
from tools.demo import COLOURS, PRACTICES

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "demo"
HOSPITAL_SLUGS = [hospital_slug(HOSPITALS[cycle]) for cycle in CYCLES]
PRACTICE_SLUGS = [hospital_slug(PRACTICES[cycle]) for cycle in CYCLES]
# Each practice sends to the hospital of the same cycle (spec §9).
PRACTICE_HOSPITAL = dict(zip(PRACTICE_SLUGS, HOSPITAL_SLUGS, strict=True))
STARTUP_SERVICES = {"prepare", "superlink", "serverapp", "register", "train"}


@cache
def config(demo_user: str | None = None) -> dict[str, Any]:
    """The file as compose reads it, with DEMO_USER set only if given."""
    environment = {k: v for k, v in os.environ.items() if k != "DEMO_USER"}
    if demo_user is not None:
        environment["DEMO_USER"] = demo_user
    result = subprocess.run(
        ["docker", "compose", "--profile", "train", "config", "--format", "json"],
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


def mounts(name: str) -> dict[str, tuple[str, bool]]:
    """Each bind mount's target, with its source relative to demo/ and whether read-only."""
    return {
        volume["target"]: (
            str(Path(volume["source"]).relative_to(DEMO)),
            bool(volume.get("read_only", False)),
        )
        for volume in service(name).get("volumes", [])
    }


def party_folder(name: str) -> str:
    """The folder under demo/ of the party a service belongs to."""
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
    assert set(config()["services"]) == STARTUP_SERVICES | {
        f"{slug}-{role}"
        for slug in HOSPITAL_SLUGS
        for role in ("supernode", "clientapp", "web", "lab-orders")
    } | {f"{slug}-{role}" for slug in PRACTICE_SLUGS for role in ("web", "reports")}


def test_each_service_mounts_only_its_own_partys_folder() -> None:
    # Setup is out of band (report, assumptions): only prepare sees every party.
    assert mounts("prepare") == {"/demo": (".", False)}
    for name in set(config()["services"]) - {"prepare"}:
        folder = party_folder(name)
        for target, (source, _) in mounts(name).items():
            assert source.startswith(folder), (name, source)
            # Every container sees a folder at the path prepare wrote it to.
            assert target == f"/demo/{source}", (name, target)


@pytest.mark.parametrize("slug", HOSPITAL_SLUGS)
def test_the_startups_code_at_a_hospital_sees_only_the_cohort_and_final_models(
    slug: str,
) -> None:
    clientapp = f"{slug}-clientapp"
    assert mounts(clientapp) == {
        f"/demo/hospitals/{slug}/cohort": (f"hospitals/{slug}/cohort", True),
        f"/demo/hospitals/{slug}/final-models": (
            f"hospitals/{slug}/final-models",
            False,
        ),
    }
    # It reaches its SuperNode and nothing else: no web app, no internet.
    assert set(service(clientapp)["networks"]) == {f"{slug}-clientapp"}
    assert config()["networks"][f"{slug}-clientapp"]["internal"] is True
    members = {
        name
        for name, spec in config()["services"].items()
        if f"{slug}-clientapp" in spec.get("networks", {})
    }
    assert members == {clientapp, f"{slug}-supernode"}


@pytest.mark.parametrize("slug", HOSPITAL_SLUGS)
@pytest.mark.parametrize("role", ["web", "lab-orders"])
def test_the_hospitals_own_apps_see_no_cohort_no_supernode_key_and_read_only_final_models(
    slug: str, role: str
) -> None:
    name = f"{slug}-{role}"
    assert set(service(name)["tmpfs"]) == {
        f"/demo/hospitals/{slug}/cohort",
        f"/demo/hospitals/{slug}/supernode",
    }
    final_models = f"/demo/hospitals/{slug}/final-models"
    assert mounts(name)[final_models] == (f"hospitals/{slug}/final-models", True)


@pytest.mark.parametrize("slug", HOSPITAL_SLUGS)
def test_the_supernode_mounts_its_key_and_ca_certificate_but_no_data(slug: str) -> None:
    assert mounts(f"{slug}-supernode") == {
        f"/demo/hospitals/{slug}/{folder}": (f"hospitals/{slug}/{folder}", True)
        for folder in ("certificates", "supernode")
    }


def test_only_the_web_apps_are_published_and_only_on_localhost() -> None:
    published = {
        (name, port["host_ip"], port["published"])
        for name, spec in config()["services"].items()
        for port in spec.get("ports", [])
    }
    assert published == {
        (f"{slug}-web", "127.0.0.1", str(first + index))
        for first, slugs in ((8001, HOSPITAL_SLUGS), (8011, PRACTICE_SLUGS))
        for index, slug in enumerate(slugs)
    }


def test_crossings_and_the_startup_are_internal_networks() -> None:
    networks = config()["networks"]
    internal = {name for name, spec in networks.items() if spec.get("internal")}
    assert internal == {"startup", "model-updates"} | {
        f"{slug}-{kind}"
        for slug in HOSPITAL_SLUGS
        for kind in ("clientapp", "lab-orders")
    }


def test_model_updates_connect_only_the_superlink_and_the_supernodes() -> None:
    members = {
        name
        for name, spec in config()["services"].items()
        if "model-updates" in spec.get("networks", {})
    }
    assert members == {"superlink"} | {f"{slug}-supernode" for slug in HOSPITAL_SLUGS}


@pytest.mark.parametrize("practice", PRACTICE_SLUGS)
def test_each_practice_reaches_only_its_own_hospitals_lab_order_endpoint(
    practice: str,
) -> None:
    hospital = PRACTICE_HOSPITAL[practice]
    for role in ("web", "reports"):
        spec = service(f"{practice}-{role}")
        assert set(spec["networks"]) == {practice, f"{hospital}-lab-orders"}
        assert spec["environment"]["MESSAGING_ADDRESS"] == f"{hospital}-lab-orders:8441"
    members = {
        name
        for name, spec in config()["services"].items()
        if f"{hospital}-lab-orders" in spec.get("networks", {})
    }
    assert members == {
        f"{hospital}-lab-orders",
        f"{practice}-web",
        f"{practice}-reports",
    }


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


def test_each_practice_checks_for_lab_reports_every_five_seconds() -> None:
    # The demo squeezes hours into seconds; a real practice checks every 60.
    for slug in PRACTICE_SLUGS:
        for role in ("web", "reports"):
            environment = service(f"{slug}-{role}")["environment"]
            assert environment["REPORT_CHECK_SECONDS"] == "5"
        assert service(f"{slug}-reports")["command"][-2:] == [
            "check_for_lab_reports",
            "--repeat",
        ]


def test_every_flower_connection_across_a_boundary_uses_tls() -> None:
    superlink = service("superlink")["command"]
    for flag in ("--ssl-ca-certfile", "--ssl-certfile", "--ssl-keyfile"):
        assert any(argument.startswith(f"{flag}=") for argument in superlink), flag
    for slug in HOSPITAL_SLUGS:
        supernode = service(f"{slug}-supernode")["command"]
        assert (
            f"--root-certificates=/demo/hospitals/{slug}/certificates/ca.crt"
            in supernode
        )
    # Only the Runtime API inside TB4's internal network goes without TLS.
    insecure = {
        name
        for name, spec in config()["services"].items()
        if "--insecure" in (spec.get("command") or [])
    }
    assert insecure == {f"{slug}-clientapp" for slug in HOSPITAL_SLUGS}


def test_the_superlink_keeps_its_state_with_the_startup() -> None:
    assert (
        "--database=/demo/startup/superlink/state.db" in service("superlink")["command"]
    )
    assert mounts("superlink")["/demo/startup/superlink"] == (
        "startup/superlink",
        False,
    )


@pytest.mark.parametrize("slug", HOSPITAL_SLUGS + PRACTICE_SLUGS)
def test_every_web_app_serves_https_with_its_partys_own_certificate(slug: str) -> None:
    name = f"{slug}-web"
    folder = party_folder(name)
    command = service(name)["command"]
    assert command[:2] == ["gunicorn", "web.wsgi"]
    assert f"--certfile=/demo/{folder}/web-tls/certificate.pem" in command
    assert f"--keyfile=/demo/{folder}/web-tls/key.pem" in command


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
    # On Linux a bind mount keeps numeric IDs: every container writes demo/ as
    # one user, by default the first account of most Linux machines.
    users = {spec.get("user") for spec in config(demo_user)["services"].values()}
    assert users == {user}
