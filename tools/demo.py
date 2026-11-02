"""Prepare the demo deployment's folders; compose.yaml runs it (spec §9).

    docker compose up --build --abort-on-container-failure
    docker compose run --rm train   # one training run, submitted inside TB2
    python tools/demo.py reset      # with the demo stopped: fresh web databases

Compose runs `prepare` and `register` from here as one-shot containers. The
startup runs the SuperLink; each hospital a SuperNode, the startup's ClientApp
in a container of its own, a web app and its lab-order endpoint; each general
practitioner's practice its own web app and a process that fetches lab reports.
"""

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from collections.abc import Callable
from functools import partial
from pathlib import Path

from tqdm import tqdm

from iron_deficiency.dataset import CYCLES, HOSPITALS, hospital_slug
from tools.certificates import Authority, covers, issue, make_authority, make_key_pair
from web.demo_accounts import (
    GENERAL_PRACTITIONERS,
    LABORATORY_DIRECTOR,
    LABORATORY_STAFF,
    PASSWORD,
)

ROOT = Path(__file__).resolve().parents[1]
# Flower 1.40 serves every SuperLink API over HTTPS on this one address, the
# SuperLink's service name in compose.yaml.
SUPERLINK = "superlink:9092"
# Where compose.yaml publishes each party's web app on the host.
FIRST_WEB_PORT = 8001
FIRST_PRACTICE_PORT = 8011
# Each practice sends its lab orders to one hospital (spec §9); fictional names.
PRACTICES = dict(
    zip(
        CYCLES,
        (
            "Huisartsenpraktijk De Akker",
            "Huisartsenpraktijk De Berk",
            "Huisartsenpraktijk De Ceder",
        ),
        strict=True,
    )
)


# Patients each practice, and so its hospital's analyser stand-in, seeds: sized
# like the hospital it sends to (large, medium, small).
PATIENTS = dict(zip(CYCLES, (40, 24, 12), strict=True))
# Each hospital's Pico colour, and its practice's from the same family.
COLOURS = dict(
    zip(
        CYCLES,
        (("jade", "green"), ("pumpkin", "amber"), ("violet", "purple")),
        strict=True,
    )
)


def startup_dir(demo_dir: Path) -> Path:
    return demo_dir / "startup"


def hospital_dir(demo_dir: Path, slug: str) -> Path:
    return demo_dir / "hospitals" / slug


def practice_dir(demo_dir: Path, slug: str) -> Path:
    return demo_dir / "practices" / slug


def hospitals() -> list[tuple[int, str]]:
    """Each hospital's partition ID and folder name, in CYCLES order."""
    return [
        (partition, hospital_slug(HOSPITALS[cycle]))
        for partition, cycle in enumerate(CYCLES)
    ]


def supernode_key(hospital: Path) -> Path:
    """The private key a hospital's SuperNode signs in with; it never leaves (R27)."""
    return hospital / "supernode" / "key"


def lab_orders_host(slug: str) -> str:
    """The hospital's lab-order endpoint in compose.yaml, which its certificate names."""
    return f"{slug}-lab-orders"


def registered_key(demo_dir: Path, slug: str) -> Path:
    """The startup's copy of a hospital's SuperNode public key, to register (R27)."""
    return startup_dir(demo_dir) / "supernodes" / f"{slug}.pub"


def practices() -> list[tuple[int, str]]:
    """Each practice's folder name, numbered as its hospital's partition."""
    return [
        (partition, hospital_slug(PRACTICES[cycle]))
        for partition, cycle in enumerate(CYCLES)
    ]


def manage(*args: str) -> list[str]:
    return [sys.executable, str(ROOT / "manage.py"), *args]


def from_hub[T](load: Callable[[], T], attempts: int = 4) -> T:
    """Load from the Hugging Face Hub, waiting out a refusal (unauthenticated limits)."""
    for attempt in range(1, attempts):
        try:
            return load()
        except (ValueError, ConnectionError):
            print(
                f"Hugging Face refused; retrying in {15 * attempt} s", file=sys.stderr
            )
            time.sleep(15 * attempt)
    return load()


def seed_arguments(partition: int, nhanes: Path) -> list[str]:
    """The same participants for a practice and its hospital: one seed and one
    number of patients per partition."""
    patients = PATIENTS[list(CYCLES)[partition]]
    return [
        "--seed",
        str(partition),
        "--nhanes",
        str(nhanes),
        "--patients",
        str(patients),
    ]


def prepare_web(folder: Path, party: str, seed_command: str, partition: int) -> None:
    """Migrate the party's database and seed its demo accounts."""
    env = {**os.environ, party: str(folder), "DJANGO_DEBUG": "1"}
    subprocess.run(manage("migrate", "-v0"), env=env, check=True)
    seed = seed_arguments(partition, folder / "nhanes.csv")
    # Quiet: the summary at startup names the accounts once.
    subprocess.run(
        manage(seed_command, *seed), env=env, check=True, stdout=subprocess.DEVNULL
    )


def prepare_flower(demo_dir: Path) -> None:
    """Create what Flower needs and is missing: the SuperLink's certificate, the
    startup's connection to it, and each hospital's copy of the startup's CA
    certificate and its own SuperNode key pair, whose public key the startup gets."""
    startup = startup_dir(demo_dir)
    certificates = startup / "certificates"
    if not (certificates / "ca.crt").exists():
        make_authority(certificates, "Demo startup")
    superlink = certificates / "superlink" / "certificate.pem"
    if not covers(superlink, SUPERLINK.split(":")[0]):
        startup_authority = Authority(
            "Demo startup", certificates / "ca.crt", certificates / "ca.key"
        )
        issue(startup_authority, superlink.parent, SUPERLINK.split(":")[0], server=True)
    # The CA certificate alone, for the startup's own clients; ca.key stays put.
    (startup / "trust").mkdir(parents=True, exist_ok=True)
    shutil.copy(certificates / "ca.crt", startup / "trust" / "ca.crt")
    (startup / "final-models").mkdir(parents=True, exist_ok=True)
    (startup / "superlink").mkdir(parents=True, exist_ok=True)
    flwr_home = startup / "flwr-home"
    flwr_home.mkdir(parents=True, exist_ok=True)
    (flwr_home / "config.toml").write_text(
        '[superlink]\ndefault = "demo"\n\n[superlink.demo]\n'
        f'address = "{SUPERLINK}"\n'
        f'root-certificates = "{startup / "trust" / "ca.crt"}"\n'
    )
    for _, slug in hospitals():
        hospital = hospital_dir(demo_dir, slug)
        # The hospital holds its own copy of the startup's CA certificate.
        (hospital / "certificates").mkdir(parents=True, exist_ok=True)
        shutil.copy(certificates / "ca.crt", hospital / "certificates" / "ca.crt")
        if not supernode_key(hospital).exists():
            make_key_pair(supernode_key(hospital))
        registered_key(demo_dir, slug).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(
            supernode_key(hospital).with_suffix(".pub"), registered_key(demo_dir, slug)
        )


def prepare(demo_dir: Path) -> None:
    """Create what is missing: Flower's keys and certificates, cohorts,
    connection, web databases."""
    from iron_deficiency.dataset import (
        load_federated_dataset,
        load_ferritin,
        load_new_samples,
    )

    prepare_flower(demo_dir)
    federated_dataset = None
    nhanes = None
    for (partition, slug), (_, practice_slug), cycle in zip(
        hospitals(), practices(), CYCLES, strict=True
    ):
        hospital = hospital_dir(demo_dir, slug)
        practice = practice_dir(demo_dir, practice_slug)
        # Each hospital is its own CA: its endpoint's certificate, its practice's.
        if not (practice / "certificates" / "certificate.pem").exists():
            authority = make_authority(hospital / "ca", HOSPITALS[cycle])
            # The practice trusts its hospital's CA, not the startup's.
            issue(authority, practice / "certificates", PRACTICES[cycle], server=False)
            shutil.copy(authority.certificate, practice / "certificates" / "ca.crt")
        endpoint = hospital / "messaging" / "certificate.pem"
        if not covers(endpoint, lab_orders_host(slug)):
            authority = Authority(
                HOSPITALS[cycle], hospital / "ca" / "ca.crt", hospital / "ca" / "ca.key"
            )
            issue(authority, endpoint.parent, lab_orders_host(slug), server=True)
        (hospital / "final-models").mkdir(parents=True, exist_ok=True)
        if not (hospital / "cohort").exists():
            federated_dataset = federated_dataset or load_federated_dataset()
            cohort = from_hub(partial(federated_dataset.load_partition, partition))
            cohort.save_to_disk(hospital / "cohort")
        # The same NHANES 2021-2023 participants: the practice's patients and
        # the hospital's analyser stand-in, loaded once.
        for folder in (hospital, practice):
            if not (folder / "nhanes.csv").exists():
                if nhanes is None:
                    nhanes = from_hub(
                        lambda: load_new_samples().merge(
                            load_ferritin(), on="sample_id", how="left"
                        )
                    )
                nhanes.to_csv(folder / "nhanes.csv", index=False)


def prepare_webs(demo_dir: Path) -> dict[str, str]:
    """Migrate and seed every party's web database, then ask each hospital for
    its screening model state, by folder name; a bar shows the slow steps."""
    webs = [
        (folder, party, seed, partition, name)
        for (partition, hospital), (_, practice), cycle in zip(
            hospitals(), practices(), CYCLES, strict=True
        )
        for folder, party, seed, name in (
            (
                hospital_dir(demo_dir, hospital),
                "HOSPITAL_DIR",
                "seed_hospital",
                HOSPITALS[cycle],
            ),
            (
                practice_dir(demo_dir, practice),
                "PRACTICE_DIR",
                "seed_practice",
                PRACTICES[cycle],
            ),
        )
    ]
    statuses = {}
    # Every step's label as wide as the longest, so the bar does not jump.
    width = len("Preparing ") + max(len(web[4]) for web in webs)
    with tqdm(total=len(webs) + len(hospitals()), unit="step", leave=False) as bar:
        for folder, party, seed, partition, name in webs:
            bar.set_description_str(f"{'Preparing ' + name:<{width}}")
            prepare_web(folder, party, seed, partition)
            bar.update()
        for (_, slug), cycle in zip(hospitals(), CYCLES, strict=True):
            bar.set_description_str(f"{'Checking ' + HOSPITALS[cycle]:<{width}}")
            statuses[slug] = screening_status(demo_dir, slug)
            bar.update()
    return statuses


def screening_status(demo_dir: Path, slug: str) -> str:
    """One hospital's one-line screening model state."""
    env = {
        **os.environ,
        "HOSPITAL_DIR": str(hospital_dir(demo_dir, slug)),
        "DJANGO_DEBUG": "1",
    }
    result = subprocess.run(
        manage("screening_status"), env=env, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def register_supernodes(demo_dir: Path, wait_seconds: int = 60) -> None:
    """Register each hospital's SuperNode public key with the SuperLink, waiting
    for it to answer; a key registered by an earlier `up` stays registered (R27)."""
    deadline = time.monotonic() + wait_seconds
    for _, slug in hospitals():
        while True:
            registration = subprocess.run(
                [
                    str(Path(sys.executable).parent / "flwr"),
                    *("supernode", "register", str(registered_key(demo_dir, slug))),
                    *("demo", "--name", slug, "--format", "json"),
                ],
                env={
                    **os.environ,
                    "FLWR_HOME": str(startup_dir(demo_dir) / "flwr-home"),
                },
                capture_output=True,
                text=True,
                check=True,
            )
            outcome = json.loads(registration.stdout)
            error = str(outcome.get("error-message", ""))
            # Flower's error code 23: this public key is registered already.
            if outcome["success"] or "[code: 23]" in error:
                break
            if "unavailable" not in error or time.monotonic() > deadline:
                raise SystemExit(f"Registering the SuperNode of {slug} failed: {error}")
            time.sleep(1)


def summary(statuses: dict[str, str]) -> str:
    """What the person starting the demo needs: where each party is, which
    account to use, and what to do next."""
    hospital_names = [HOSPITALS[cycle] for cycle in CYCLES]
    practice_names = [f"{PRACTICES[cycle]} → {HOSPITALS[cycle]}" for cycle in CYCLES]
    lines = [
        f"Demo prepared. Password for every account: {PASSWORD}",
        "",
        (
            f"Hospitals   laboratory staff: {LABORATORY_STAFF}"
            f" · laboratory director: {LABORATORY_DIRECTOR}"
        ),
    ]
    for (partition, slug), name in zip(hospitals(), hospital_names, strict=True):
        url = f"http://127.0.0.1:{FIRST_WEB_PORT + partition}/"
        width = max(map(len, hospital_names))
        lines.append(f"  {name:<{width}}  {url}   {statuses[slug]}")
    lines += [
        "",
        f"Practices   general practitioners: {', '.join(GENERAL_PRACTITIONERS)}",
    ]
    for (partition, _), name in zip(practices(), practice_names, strict=True):
        lines.append(
            f"  {name:<{max(map(len, practice_names))}}"
            f"  http://127.0.0.1:{FIRST_PRACTICE_PORT + partition}/"
        )
    lines.append("")
    if any(status == "no screening model yet" for status in statuses.values()):
        lines.append(
            "Next: train with `docker compose run --rm train` in another"
            f" terminal, then deploy as {LABORATORY_DIRECTOR}."
        )
    elif any(status.endswith("none deployed") for status in statuses.values()):
        lines.append(
            f"Next: deploy a screening model as {LABORATORY_DIRECTOR} where none is."
        )
    lines.append("Logs: `docker compose logs <service>` · Ctrl-C stops every party.")
    return "\n".join(lines)


def web_app_listening() -> bool:
    """Whether the first hospital's web app answers: the demo is up."""
    with socket.socket() as probe:
        return probe.connect_ex(("127.0.0.1", FIRST_WEB_PORT)) == 0


def reset(demo_dir: Path, demo_running: Callable[[], bool] = web_app_listening) -> None:
    """Remove every party's web database, so the next `up` migrates and seeds
    afresh. Certificates, cohorts, final models and NHANES data stay."""
    if demo_running():
        raise SystemExit("Stop the demo (Ctrl-C) before resetting it.")
    for database in sorted(demo_dir.glob("*/*/web.sqlite3")):
        database.unlink()
        print(f"Removed {database.relative_to(demo_dir)}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "register", "reset"])
    parser.add_argument("--demo-dir", type=Path, default=ROOT / "demo")
    args = parser.parse_args()
    demo_dir = args.demo_dir.resolve()
    if args.action == "prepare":
        prepare(demo_dir)
        print(summary(prepare_webs(demo_dir)), flush=True)
    elif args.action == "register":
        register_supernodes(demo_dir)
    else:
        reset(demo_dir)


if __name__ == "__main__":
    main()
