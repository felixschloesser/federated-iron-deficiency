"""Prepare the demo deployment's folders; compose.yaml runs it (spec §9).

    docker compose up --build --abort-on-container-failure
    docker compose run --rm train   # one training run, submitted inside TB2
    docker compose down -v          # start over; demo/ on the host stays

Compose runs `prepare` from here as a one-shot container, each
party's folder a volume of its own. The startup runs the SuperLink; each
hospital a SuperNode, the startup's ClientApp in a container of its own, and
one container for its web app and lab-order endpoint; each general
practitioner's practice its own web app.
"""

import argparse
import os
import subprocess
import sys
import time
import tomllib
from collections.abc import Callable
from functools import partial
from pathlib import Path

from tqdm import tqdm

from iron_deficiency.dataset import CYCLES, HOSPITALS, hospital_slug
from web.seeding.accounts import (
    GENERAL_PRACTITIONER,
    LABORATORY_DIRECTOR,
    LABORATORY_STAFF,
    PASSWORD,
)

ROOT = Path(__file__).resolve().parents[1]
# Flower 1.40 serves every SuperLink API on this one address, the
# SuperLink's service name in compose.yaml.
SUPERLINK = "flower-superlink:9092"
# The demo's parties, declared in demo.toml; keyed here by cycle, like HOSPITALS.
PARTIES = tomllib.loads((ROOT / "demo.toml").read_text())["hospitals"]
_ENTRIES = {cycle: PARTIES[hospital_slug(name)] for cycle, name in HOSPITALS.items()}
# Each practice is paired with a hospital for its colour and patients (spec §9);
# it may send samples to every hospital's laboratory (R22).
PRACTICES: dict[str, str] = {
    cycle: entry["practice"] for cycle, entry in _ENTRIES.items()
}
# Patients each practice, and so its hospital's analyser stand-in, seeds.
PATIENTS: dict[str, int] = {
    cycle: entry["patients"] for cycle, entry in _ENTRIES.items()
}
# Each hospital's Pico colour, and its practice's from the same family.
COLOURS: dict[str, tuple[str, str]] = {
    cycle: (entry["colour"], entry["practice_colour"])
    for cycle, entry in _ENTRIES.items()
}


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


def lab_orders_host(slug: str) -> str:
    """The hospital's lab-order endpoint in compose.yaml."""
    return f"{slug}-lab-orders"


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


def add_laboratories(practice: Path) -> None:
    """Every hospital's laboratory, at its lab-order endpoint (R22)."""
    env = {**os.environ, "PRACTICE_DIR": str(practice), "DJANGO_DEBUG": "1"}
    for (_, slug), cycle in zip(hospitals(), CYCLES, strict=True):
        address = f"{lab_orders_host(slug)}:8441"
        subprocess.run(
            manage("add_laboratory", HOSPITALS[cycle], address),
            env=env,
            check=True,
            stdout=subprocess.DEVNULL,
        )


def prepare_flower(demo_dir: Path) -> None:
    """Create the startup's connection to the SuperLink, plaintext: the report's
    TLS and SuperNode authentication are left out of the demo for simplicity."""
    startup = startup_dir(demo_dir)
    (startup / "final-models").mkdir(parents=True, exist_ok=True)
    (startup / "superlink").mkdir(parents=True, exist_ok=True)
    flwr_home = startup / "flwr-home"
    flwr_home.mkdir(parents=True, exist_ok=True)
    (flwr_home / "config.toml").write_text(
        '[superlink]\ndefault = "demo"\n\n[superlink.demo]\n'
        f'address = "{SUPERLINK}"\ninsecure = true\n'
    )


def prepare(demo_dir: Path) -> None:
    """Create what is missing: Flower's connection, cohorts, the NHANES data."""
    from iron_deficiency.dataset import (
        load_federated_dataset,
        load_ferritin,
        load_new_samples,
    )

    prepare_flower(demo_dir)
    federated_dataset = None
    nhanes = None
    for (partition, slug), (_, practice_slug), _cycle in zip(
        hospitals(), practices(), CYCLES, strict=True
    ):
        hospital = hospital_dir(demo_dir, slug)
        practice = practice_dir(demo_dir, practice_slug)
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
            if party == "PRACTICE_DIR":
                add_laboratories(folder)
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


def web_address(slug: str, http_port: int) -> str:
    """Where a browser finds a party's web app, through the proxy."""
    port = "" if http_port == 80 else f":{http_port}"
    return f"http://{slug}.localhost{port}/"


def summary(statuses: dict[str, str], http_port: int = 80) -> str:
    """What the person starting the demo needs: where each party is, which
    account to use, and what to do next."""
    hospital_names = [HOSPITALS[cycle] for cycle in CYCLES]
    practice_names = [PRACTICES[cycle] for cycle in CYCLES]
    lines = [
        f"Demo prepared. Password for every account: {PASSWORD}",
        "",
        (
            f"Hospitals   laboratory staff: {LABORATORY_STAFF}"
            f" · laboratory director: {LABORATORY_DIRECTOR}"
        ),
    ]
    for (_, slug), name in zip(hospitals(), hospital_names, strict=True):
        url = web_address(slug, http_port)
        width = max(map(len, hospital_names))
        lines.append(f"  {name:<{width}}  {url}   {statuses[slug]}")
    lines += [
        "",
        f"Practices   general practitioner: {GENERAL_PRACTITIONER}",
    ]
    for (_, slug), name in zip(practices(), practice_names, strict=True):
        lines.append(
            f"  {name:<{max(map(len, practice_names))}}  {web_address(slug, http_port)}"
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare"])
    parser.add_argument("--demo-dir", type=Path, default=ROOT / "demo")
    args = parser.parse_args()
    demo_dir = args.demo_dir.resolve()
    prepare(demo_dir)
    http_port = int(os.environ.get("DEMO_HTTP_PORT", "80"))
    print(summary(prepare_webs(demo_dir), http_port), flush=True)


if __name__ == "__main__":
    main()
