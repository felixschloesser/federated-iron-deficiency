"""Run the demo deployment: one folder and one process per party (spec §9).

    python tools/demo.py up      # prepare demo/, start every party, Ctrl-C stops
    python tools/demo.py train   # in a second terminal: one training run over TLS
    python tools/demo.py reset   # with the demo stopped: fresh web databases

The startup runs the SuperLink; each hospital runs a SuperNode, a web app and
its messaging endpoint; each general practitioner's practice runs its own web
app and fetches lab reports from its one hospital. Each sees only its own folder.
"""

import argparse
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from types import FrameType
from typing import NoReturn

from tqdm import tqdm

from iron_deficiency.dataset import CYCLES, HOSPITALS, hospital_slug
from tools.certificates import issue, make_authority
from web.demo_accounts import (
    GENERAL_PRACTITIONERS,
    LABORATORY_DIRECTOR,
    LABORATORY_STAFF,
    PASSWORD,
)

ROOT = Path(__file__).resolve().parents[1]
# Flower 1.40 serves every SuperLink API over HTTPS on this one address.
SUPERLINK = "127.0.0.1:9092"
FIRST_WEB_PORT = 8001
FIRST_PRACTICE_PORT = 8011
FIRST_MESSAGING_PORT = 8441
FIRST_RUNTIME_PORT = 9094
# The demo squeezes hours into seconds; a real practice checks every 60.
REPORT_CHECK_SECONDS = 5
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


# Each hospital's Pico colour, and its practice's from the same family.
COLOURS = dict(
    zip(
        CYCLES,
        (("jade", "green"), ("pumpkin", "amber"), ("violet", "purple")),
        strict=True,
    )
)


@dataclass(frozen=True)
class Process:
    name: str
    folder: Path
    command: list[str]
    env: dict[str, str] = field(default_factory=dict)


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


def practices() -> list[tuple[int, str]]:
    """Each practice's folder name, numbered as its hospital's partition."""
    return [
        (partition, hospital_slug(PRACTICES[cycle]))
        for partition, cycle in enumerate(CYCLES)
    ]


def manage(*args: str) -> list[str]:
    return [sys.executable, str(ROOT / "manage.py"), *args]


def plan(demo_dir: Path) -> list[Process]:
    """The processes of the demo deployment, each given only its party's paths."""
    flower = Path(sys.executable).parent
    startup = startup_dir(demo_dir)
    certificates = startup / "certificates"
    processes = [
        Process(
            "superlink",
            startup,
            [
                str(flower / "flower-superlink"),
                *("--host", SUPERLINK.split(":")[0]),
                *("--port", SUPERLINK.split(":")[1]),
                *("--database", str(startup / "superlink" / "state.db")),
                # Run the ServerApp in this environment: a fresh one per run
                # took minutes to import torch, past the SuperLink's heartbeat.
                "--disable-runtime-dependency-installation",
                *("--ssl-ca-certfile", str(certificates / "ca.crt")),
                *(
                    "--ssl-certfile",
                    str(certificates / "superlink" / "certificate.pem"),
                ),
                *("--ssl-keyfile", str(certificates / "superlink" / "key.pem")),
            ],
            {"FLWR_HOME": str(startup / "flwr-home")},
        )
    ]
    for (partition, slug), cycle in zip(hospitals(), CYCLES, strict=True):
        hospital = hospital_dir(demo_dir, slug)
        node_config = (
            f"data-path='{hospital / 'cohort'}' "
            f"final-models-path='{hospital / 'final-models'}'"
        )
        party = {"HOSPITAL_DIR": str(hospital), "DJANGO_DEBUG": "1"}
        processes += [
            Process(
                f"supernode {slug}",
                hospital,
                [
                    str(flower / "flower-supernode"),
                    *("--superlink", SUPERLINK),
                    *("--root-certificates", str(hospital / "certificates" / "ca.crt")),
                    *("--host", "127.0.0.1"),
                    *("--port", str(FIRST_RUNTIME_PORT + partition)),
                    *("--node-config", node_config),
                ],
                {"FLWR_HOME": str(hospital / "flwr-home")},
            ),
            Process(
                f"web {slug}",
                hospital,
                manage(
                    "runserver", "--noreload", f"127.0.0.1:{FIRST_WEB_PORT + partition}"
                ),
                {
                    **party,
                    "HOSPITAL_NAME": HOSPITALS[cycle],
                    "PARTY_COLOUR": COLOURS[cycle][0],
                },
            ),
            Process(
                f"messaging {slug}",
                hospital,
                manage(
                    "serve_messages", f"127.0.0.1:{FIRST_MESSAGING_PORT + partition}"
                ),
                party,
            ),
        ]
    for (partition, slug), cycle in zip(practices(), CYCLES, strict=True):
        practice = practice_dir(demo_dir, slug)
        party = {
            "PRACTICE_DIR": str(practice),
            "MESSAGING_ADDRESS": f"127.0.0.1:{FIRST_MESSAGING_PORT + partition}",
            "REPORT_CHECK_SECONDS": str(REPORT_CHECK_SECONDS),
            "DJANGO_DEBUG": "1",
        }
        processes += [
            Process(
                f"web {slug}",
                practice,
                manage(
                    "runserver",
                    "--noreload",
                    f"127.0.0.1:{FIRST_PRACTICE_PORT + partition}",
                ),
                {
                    **party,
                    "PRACTICE_NAME": PRACTICES[cycle],
                    "PARTY_COLOUR": COLOURS[cycle][1],
                },
            ),
            Process(
                f"reports {slug}",
                practice,
                manage("check_for_lab_reports", "--repeat"),
                party,
            ),
        ]
    return processes


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


def prepare_web(folder: Path, party: str, seed_command: str, partition: int) -> None:
    """Migrate the party's database and seed its demo accounts."""
    env = {**os.environ, party: str(folder), "DJANGO_DEBUG": "1"}
    subprocess.run(manage("migrate", "-v0"), env=env, check=True)
    seed = ("--seed", str(partition), "--nhanes", str(folder / "nhanes.csv"))
    # Quiet: the summary at startup names the accounts once.
    subprocess.run(
        manage(seed_command, *seed), env=env, check=True, stdout=subprocess.DEVNULL
    )


def prepare(demo_dir: Path) -> None:
    """Create what is missing: certificates, cohorts, connection, web databases."""
    from iron_deficiency.dataset import (
        load_federated_dataset,
        load_ferritin,
        load_new_samples,
    )

    startup = startup_dir(demo_dir)
    certificates = startup / "certificates"
    if not (certificates / "superlink" / "certificate.pem").exists():
        startup_authority = make_authority(certificates, "Demo startup")
        issue(startup_authority, certificates / "superlink", "localhost", server=True)
    (startup / "superlink").mkdir(parents=True, exist_ok=True)
    flwr_home = startup / "flwr-home"
    flwr_home.mkdir(parents=True, exist_ok=True)
    (flwr_home / "config.toml").write_text(
        '[superlink]\ndefault = "demo"\n\n[superlink.demo]\n'
        f'address = "{SUPERLINK}"\n'
        f'root-certificates = "{certificates / "ca.crt"}"\n'
    )
    federated_dataset = None
    nhanes = None
    for (partition, slug), (_, practice_slug), cycle in zip(
        hospitals(), practices(), CYCLES, strict=True
    ):
        hospital = hospital_dir(demo_dir, slug)
        practice = practice_dir(demo_dir, practice_slug)
        # The hospital holds its own copy of the startup's CA certificate.
        (hospital / "certificates").mkdir(parents=True, exist_ok=True)
        shutil.copy(certificates / "ca.crt", hospital / "certificates" / "ca.crt")
        # Each hospital is its own CA: its endpoint's certificate, its practice's.
        if not (practice / "certificates" / "certificate.pem").exists():
            authority = make_authority(hospital / "ca", HOSPITALS[cycle])
            issue(authority, hospital / "messaging", "localhost", server=True)
            # The practice trusts its hospital's CA, not the startup's.
            issue(authority, practice / "certificates", PRACTICES[cycle], server=False)
            shutil.copy(authority.certificate, practice / "certificates" / "ca.crt")
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


def summary(statuses: dict[str, str]) -> str:
    """What the person starting the demo needs: where each party is, which
    account to use, and what to do next."""
    hospital_names = [HOSPITALS[cycle] for cycle in CYCLES]
    practice_names = [f"{PRACTICES[cycle]} → {HOSPITALS[cycle]}" for cycle in CYCLES]
    lines = [
        f"Demo up. Password for every account: {PASSWORD}",
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
            "Next: train with `uv run python tools/demo.py train` in another"
            f" terminal, then deploy as {LABORATORY_DIRECTOR}."
        )
    elif any(status.endswith("none deployed") for status in statuses.values()):
        lines.append(
            f"Next: deploy a screening model as {LABORATORY_DIRECTOR} where none is."
        )
    lines.append("Logs: demo/<party folder>/*.out · Ctrl-C stops every party.")
    return "\n".join(lines)


def stop(signum: int, frame: FrameType | None) -> NoReturn:
    """Start the clean-up, ignoring later signals: `uv run` forwards a second
    one, which must not cut the clean-up short and orphan the children."""
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    raise KeyboardInterrupt


def up(demo_dir: Path) -> None:
    """Start every party; stop them all on Ctrl-C or when one exits."""
    prepare(demo_dir)
    statuses = prepare_webs(demo_dir)
    # Stop the children on SIGTERM too, not only on Ctrl-C.
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    running: list[subprocess.Popen[bytes]] = []
    try:
        for process in plan(demo_dir):
            output = (process.folder / f"{process.name.split()[0]}.out").open("wb")
            running.append(
                subprocess.Popen(
                    process.command,
                    env={**os.environ, **process.env},
                    stdout=output,
                    stderr=subprocess.STDOUT,
                )
            )
        print(summary(statuses), flush=True)
        while all(child.poll() is None for child in running):
            time.sleep(1)
        print("A party stopped; stopping the others.", file=sys.stderr)
    except KeyboardInterrupt:
        pass
    finally:
        for child in running:
            child.terminate()
        for child in running:
            child.wait()


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


def train(demo_dir: Path) -> None:
    """Submit one training run to the demo SuperLink, over TLS."""
    subprocess.run(
        [
            str(Path(sys.executable).parent / "flwr"),
            "run",
            str(ROOT),
            "demo",
            "--run-config",
            f"demo-dir='{demo_dir}'",
            "--stream",
        ],
        env={**os.environ, "FLWR_HOME": str(startup_dir(demo_dir) / "flwr-home")},
        check=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["up", "train", "reset"])
    parser.add_argument("--demo-dir", type=Path, default=ROOT / "demo")
    args = parser.parse_args()
    demo_dir = args.demo_dir.resolve()
    actions = {"up": up, "train": train, "reset": reset}
    actions[args.action](demo_dir)


if __name__ == "__main__":
    main()
