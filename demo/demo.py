"""Prepare the demo's folders; compose.yaml runs it (demo/README.md).

    docker compose up --build --abort-on-container-failure
    docker compose run --rm train   # one training run, submitted inside TB2;
                                    # or on the startup's web app
    docker compose down -v          # start over; .demo/ on the host stays

Compose runs `prepare` from here as a one-shot container, each
party's folder a volume of its own. The startup runs the SuperLink and its own web app; each
hospital a SuperNode, the startup's ClientApp in a container of its own, and
one container for its web app and lab-order endpoint; each general
practitioner's practice its own web app.
"""

import argparse
import os
import subprocess
import sys
import time
from collections.abc import Callable
from functools import partial
from pathlib import Path

from tqdm import tqdm

from demo.topology import PATIENTS, PRACTICES
from ml.dataset import CYCLES, HOSPITALS, hospital_slug
from web.seeding.accounts import (
    DATA_SCIENTIST,
    GENERAL_PRACTITIONER,
    LABORATORY_DIRECTOR,
    LABORATORY_STAFF,
    PASSWORD,
)

ROOT = Path(__file__).resolve().parents[1]
# Flower 1.40 serves every SuperLink API on this one address, the
# SuperLink's service name in compose.yaml.
SUPERLINK = "flower-superlink:9092"


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


def messaging_host(slug: str) -> str:
    """The hospital's lab-order endpoint in compose.yaml."""
    return f"{slug}-messaging"


def nhanes_csv(demo_dir: Path) -> Path:
    """The NHANES cycle the seed commands pick participants from: beside the
    downloads it comes from, which only prepare mounts, never in a party's folder."""
    return demo_dir / "huggingface" / "nhanes-2021-2023.csv"


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
    """One practice's participants: one seed and one number of patients per
    partition, sized like its paired hospital."""
    patients = PATIENTS[list(CYCLES)[partition]]
    return [
        "--seed",
        str(partition),
        "--nhanes",
        str(nhanes),
        "--patients",
        str(patients),
    ]


def tube_seeds(nhanes: Path) -> list[list[str]]:
    """Every practice's participants, for a hospital's analyser stand-in: any
    practice may send it a sample (features/messaging.feature)."""
    return [seed_arguments(partition, nhanes) for partition, _ in hospitals()]


def prepare_web(
    folder: Path, party: str, seed_command: str, seeds: list[list[str]]
) -> None:
    """Migrate the party's database and seed its demo accounts, once per seed."""
    env = {**os.environ, "PARTY": party, "DATA_DIR": str(folder), "DJANGO_DEBUG": "1"}
    subprocess.run(manage("migrate", "-v0"), env=env, check=True)
    for seed in seeds:
        # Quiet: the summary at startup names the accounts once.
        subprocess.run(
            manage(seed_command, *seed), env=env, check=True, stdout=subprocess.DEVNULL
        )


def laboratory_arguments(practice_cycle: str) -> list[list[str]]:
    """add_laboratory's arguments for every hospital's laboratory; the practice's
    paired hospital's is its primary laboratory, so by default lab orders follow
    the hospitals' sizes (features/ordering.feature)."""
    return [
        [
            HOSPITALS[cycle],
            f"{messaging_host(slug)}:8441",
            *(["--primary"] if cycle == practice_cycle else []),
        ]
        for (_, slug), cycle in zip(hospitals(), CYCLES, strict=True)
    ]


def practice_arguments() -> list[list[str]]:
    """add_practice's arguments for every practice, its certificate name its
    folder name: every hospital knows them all, as every practice may send it a
    sample (features/messaging.feature)."""
    return [
        [slug, PRACTICES[cycle]]
        for (_, slug), cycle in zip(practices(), CYCLES, strict=True)
    ]


def add_practices(hospital: Path) -> None:
    """Every practice, at the hospital, by its certificate name."""
    env = {
        **os.environ,
        "PARTY": "hospital",
        "DATA_DIR": str(hospital),
        "DJANGO_DEBUG": "1",
    }
    for arguments in practice_arguments():
        subprocess.run(
            manage("add_practice", *arguments),
            env=env,
            check=True,
            stdout=subprocess.DEVNULL,
        )


def add_laboratories(practice: Path, practice_cycle: str) -> None:
    """Every hospital's laboratory, at its lab-order endpoint (features/messaging.feature)."""
    env = {
        **os.environ,
        "PARTY": "practice",
        "DATA_DIR": str(practice),
        "DJANGO_DEBUG": "1",
    }
    for arguments in laboratory_arguments(practice_cycle):
        subprocess.run(
            manage("add_laboratory", *arguments),
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
    from ml.dataset import (
        load_federated_dataset,
        load_ferritin,
        load_new_samples,
    )

    prepare_flower(demo_dir)
    federated_dataset = None
    for (partition, slug), (_, practice_slug), _cycle in zip(
        hospitals(), practices(), CYCLES, strict=True
    ):
        hospital = hospital_dir(demo_dir, slug)
        practice = practice_dir(demo_dir, practice_slug)
        # Folders prepared before the rename keep their models.
        if (hospital / "final-models").exists() and not (
            hospital / "screening-models"
        ).exists():
            (hospital / "final-models").rename(hospital / "screening-models")
        (hospital / "screening-models").mkdir(parents=True, exist_ok=True)
        practice.mkdir(parents=True, exist_ok=True)
        if not (hospital / "cohort").exists():
            federated_dataset = federated_dataset or load_federated_dataset()
            cohort = from_hub(partial(federated_dataset.load_partition, partition))
            cohort.save_to_disk(hospital / "cohort")
        # Folders prepared before the cycle stayed with prepare held a copy.
        for folder in (hospital, practice):
            (folder / "nhanes.csv").unlink(missing_ok=True)
    # The same NHANES 2021-2023 participants: the practices' patients and the
    # hospitals' analyser stand-in.
    if not nhanes_csv(demo_dir).exists():
        nhanes_csv(demo_dir).parent.mkdir(parents=True, exist_ok=True)
        nhanes = from_hub(
            lambda: load_new_samples().merge(
                load_ferritin(), on="sample_id", how="left"
            )
        )
        nhanes.to_csv(nhanes_csv(demo_dir), index=False)


def prepare_webs(demo_dir: Path) -> dict[str, str]:
    """Migrate and seed every party's web database, then ask each hospital for
    its screening model state, by folder name; a bar shows the slow steps."""
    nhanes = nhanes_csv(demo_dir)
    # A hospital's analyser stand-in holds every practice's tubes; a practice
    # seeds only its own patients.
    webs = [
        web
        for (partition, hospital), (_, practice), cycle in zip(
            hospitals(), practices(), CYCLES, strict=True
        )
        for web in (
            (
                hospital_dir(demo_dir, hospital),
                "hospital",
                "seed_hospital",
                tube_seeds(nhanes),
                HOSPITALS[cycle],
                cycle,
            ),
            (
                practice_dir(demo_dir, practice),
                "practice",
                "seed_practice",
                [seed_arguments(partition, nhanes)],
                PRACTICES[cycle],
                cycle,
            ),
        )
    ]
    # The startup's web app seeds only its data scientist, once.
    webs.insert(
        0,
        (startup_dir(demo_dir), "startup", "seed_startup", [[]], "the startup", ""),
    )
    statuses = {}
    # Every step's label as wide as the longest, so the bar does not jump.
    width = len("Preparing ") + max(len(web[4]) for web in webs)
    with tqdm(total=len(webs) + len(hospitals()), unit="step", leave=False) as bar:
        for folder, party, seed_command, seeds, name, cycle in webs:
            bar.set_description_str(f"{'Preparing ' + name:<{width}}")
            prepare_web(folder, party, seed_command, seeds)
            if party == "practice":
                add_laboratories(folder, cycle)
            if party == "hospital":
                add_practices(folder)
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
        "PARTY": "hospital",
        "DATA_DIR": str(hospital_dir(demo_dir, slug)),
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
        f"Startup     data scientist: {DATA_SCIENTIST}",
        f"  {web_address('startup', http_port)}",
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
            f"Next: submit a training run as {DATA_SCIENTIST} (or"
            " `docker compose run --rm train` in another terminal), then deploy"
            f" as {LABORATORY_DIRECTOR}."
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
    parser.add_argument("--demo-dir", type=Path, default=ROOT / ".demo")
    args = parser.parse_args()
    demo_dir = args.demo_dir.resolve()
    prepare(demo_dir)
    http_port = int(os.environ.get("DEMO_HTTP_PORT", "80"))
    print(summary(prepare_webs(demo_dir), http_port), flush=True)


if __name__ == "__main__":
    main()
