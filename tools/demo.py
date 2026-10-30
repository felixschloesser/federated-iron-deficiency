"""Run the demo deployment: one folder and one process per party (spec §9).

    python tools/demo.py up      # prepare demo/, start every party, Ctrl-C stops
    python tools/demo.py train   # in a second terminal: one training run over TLS

The startup runs the SuperLink; each hospital runs a SuperNode, a web app and
its messaging endpoint; each general practitioner's practice runs its own web
app and fetches lab reports from its one hospital. Each sees only its own folder.
"""

import argparse
import os
import shutil
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path

from iron_deficiency.dataset import CYCLES, HOSPITALS, hospital_slug
from tools.certificates import issue, make_authority

ROOT = Path(__file__).resolve().parents[1]
# Flower 1.40 serves every SuperLink API over HTTPS on this one address.
SUPERLINK = "127.0.0.1:9092"
FIRST_WEB_PORT = 8001
FIRST_PRACTICE_PORT = 8011
FIRST_MESSAGING_PORT = 8441
FIRST_RUNTIME_PORT = 9094
REPORT_CHECK_SECONDS = 60
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
                {**party, "HOSPITAL_NAME": HOSPITALS[cycle]},
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
                {**party, "PRACTICE_NAME": PRACTICES[cycle]},
            ),
            Process(
                f"reports {slug}",
                practice,
                manage("check_for_lab_reports", "--every", str(REPORT_CHECK_SECONDS)),
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


def prepare_web(folder: Path, party: str, partition: int) -> None:
    """Migrate the party's database and seed its demo accounts."""
    env = {**os.environ, party: str(folder), "DJANGO_DEBUG": "1"}
    subprocess.run(manage("migrate", "-v0"), env=env, check=True)
    seed = ("--seed", str(partition), "--nhanes", str(folder / "nhanes.csv"))
    subprocess.run(manage("seed_demo", *seed), env=env, check=True)


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
        prepare_web(hospital, "HOSPITAL_DIR", partition)
        prepare_web(practice, "PRACTICE_DIR", partition)


def up(demo_dir: Path) -> None:
    """Start every party; stop them all on Ctrl-C or when one exits."""
    prepare(demo_dir)
    # Stop the children on SIGTERM too, not only on Ctrl-C.
    signal.signal(signal.SIGTERM, signal.default_int_handler)
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
        for partition, slug in hospitals():
            print(f"{slug}: http://127.0.0.1:{FIRST_WEB_PORT + partition}/", flush=True)
        for partition, slug in practices():
            port = FIRST_PRACTICE_PORT + partition
            print(f"{slug}: http://127.0.0.1:{port}/", flush=True)
        print(
            "Train with: python tools/demo.py train. Ctrl-C stops every party.",
            flush=True,
        )
        while all(child.poll() is None for child in running):
            time.sleep(1)
        print("A party stopped; stopping the others.", file=sys.stderr)
    except KeyboardInterrupt:
        pass
    finally:
        # A second signal (uv run forwards them) must not cut the clean-up short.
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        for child in running:
            child.terminate()
        for child in running:
            child.wait()


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
    parser.add_argument("action", choices=["up", "train"])
    parser.add_argument("--demo-dir", type=Path, default=ROOT / "demo")
    args = parser.parse_args()
    demo_dir = args.demo_dir.resolve()
    up(demo_dir) if args.action == "up" else train(demo_dir)


if __name__ == "__main__":
    main()
