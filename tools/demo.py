"""Run the demo deployment: one folder and one process per party (spec §9).

    python tools/demo.py up      # prepare demo/, start every party, Ctrl-C stops
    python tools/demo.py train   # in a second terminal: one training run over TLS

The startup runs the SuperLink; each hospital runs a SuperNode and a web app,
and sees only its own folder under demo/hospitals/.
"""

import argparse
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path

from iron_deficiency.dataset import CYCLES, HOSPITALS

ROOT = Path(__file__).resolve().parents[1]
# Flower 1.40 serves every SuperLink API over HTTPS on this one address.
SUPERLINK = "127.0.0.1:9092"
FIRST_WEB_PORT = 8001
FIRST_RUNTIME_PORT = 9094


@dataclass(frozen=True)
class Process:
    name: str
    command: list[str]
    env: dict[str, str] = field(default_factory=dict)


def startup_dir(demo_dir: Path) -> Path:
    return demo_dir / "startup"


def hospital_dir(demo_dir: Path, slug: str) -> Path:
    return demo_dir / "hospitals" / slug


def hospitals() -> list[tuple[int, str]]:
    """Each hospital's partition ID and folder name, in CYCLES order."""
    return [(partition, HOSPITALS[cycle]) for partition, cycle in enumerate(CYCLES)]


def plan(demo_dir: Path) -> list[Process]:
    """The processes of the demo deployment, each given only its party's paths."""
    flower = Path(sys.executable).parent
    startup = startup_dir(demo_dir)
    certificates = startup / "certificates"
    processes = [
        Process(
            "superlink",
            [
                str(flower / "flower-superlink"),
                *("--host", SUPERLINK.split(":")[0]),
                *("--port", SUPERLINK.split(":")[1]),
                *("--database", str(startup / "superlink" / "state.db")),
                # Run the ServerApp in this environment: a fresh one per run
                # took minutes to import torch, past the SuperLink's heartbeat.
                "--disable-runtime-dependency-installation",
                *("--ssl-ca-certfile", str(certificates / "ca.crt")),
                *("--ssl-certfile", str(certificates / "server.pem")),
                *("--ssl-keyfile", str(certificates / "server.key")),
            ],
            {"FLWR_HOME": str(startup / "flwr-home")},
        )
    ]
    for partition, slug in hospitals():
        hospital = hospital_dir(demo_dir, slug)
        node_config = (
            f"data-path='{hospital / 'cohort'}' "
            f"final-models-path='{hospital / 'final-models'}'"
        )
        processes.append(
            Process(
                f"supernode {slug}",
                [
                    str(flower / "flower-supernode"),
                    *("--superlink", SUPERLINK),
                    *("--root-certificates", str(hospital / "certificates" / "ca.crt")),
                    *("--host", "127.0.0.1"),
                    *("--port", str(FIRST_RUNTIME_PORT + partition)),
                    *("--node-config", node_config),
                ],
                {"FLWR_HOME": str(hospital / "flwr-home")},
            )
        )
        processes.append(
            Process(
                f"web {slug}",
                [
                    sys.executable,
                    str(ROOT / "manage.py"),
                    "runserver",
                    "--noreload",
                    f"127.0.0.1:{FIRST_WEB_PORT + partition}",
                ],
                {"HOSPITAL_DIR": str(hospital), "DJANGO_DEBUG": "1"},
            )
        )
    return processes


def make_certificates(certificates: Path) -> None:
    """A self-signed CA and a SuperLink certificate for localhost."""
    certificates.mkdir(parents=True, exist_ok=True)

    def openssl(*args: str) -> None:
        subprocess.run(
            ["openssl", *args], cwd=certificates, check=True, capture_output=True
        )

    openssl(
        "req",
        "-x509",
        "-newkey",
        "rsa:2048",
        "-nodes",
        "-days",
        "30",
        "-subj",
        "/CN=Demo startup CA",
        "-keyout",
        "ca.key",
        "-out",
        "ca.crt",
    )
    openssl(
        "req",
        "-newkey",
        "rsa:2048",
        "-nodes",
        "-subj",
        "/CN=localhost",
        "-keyout",
        "server.key",
        "-out",
        "server.csr",
    )
    with tempfile.NamedTemporaryFile("w", suffix=".ext") as extensions:
        extensions.write("subjectAltName=DNS:localhost,IP:127.0.0.1\n")
        extensions.flush()
        openssl(
            "x509",
            "-req",
            "-in",
            "server.csr",
            "-CA",
            "ca.crt",
            "-CAkey",
            "ca.key",
            "-CAcreateserial",
            "-days",
            "30",
            "-out",
            "server.pem",
            "-extfile",
            extensions.name,
        )


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


def prepare(demo_dir: Path) -> None:
    """Create what is missing: certificates, cohorts, connection, web databases."""
    from iron_deficiency.dataset import (
        load_federated_dataset,
        load_ferritin,
        load_new_samples,
    )

    startup = startup_dir(demo_dir)
    certificates = startup / "certificates"
    if not (certificates / "ca.crt").exists():
        make_certificates(certificates)
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
    for partition, slug in hospitals():
        hospital = hospital_dir(demo_dir, slug)
        # The hospital holds its own copy of the startup's CA certificate.
        (hospital / "certificates").mkdir(parents=True, exist_ok=True)
        shutil.copy(certificates / "ca.crt", hospital / "certificates" / "ca.crt")
        if not (hospital / "cohort").exists():
            federated_dataset = federated_dataset or load_federated_dataset()
            cohort = from_hub(partial(federated_dataset.load_partition, partition))
            cohort.save_to_disk(hospital / "cohort")
        # The hospital's patients come from NHANES 2021-2023, loaded once.
        if not (hospital / "nhanes.csv").exists():
            if nhanes is None:
                nhanes = from_hub(
                    lambda: load_new_samples().merge(
                        load_ferritin(), on="sample_id", how="left"
                    )
                )
            nhanes.to_csv(hospital / "nhanes.csv", index=False)
        web = {**os.environ, "HOSPITAL_DIR": str(hospital), "DJANGO_DEBUG": "1"}
        manage = [sys.executable, str(ROOT / "manage.py")]
        subprocess.run([*manage, "migrate", "-v0"], env=web, check=True)
        seed = [
            "seed_demo",
            "--seed",
            str(partition),
            "--nhanes",
            str(hospital / "nhanes.csv"),
        ]
        subprocess.run([*manage, *seed], env=web, check=True)


def up(demo_dir: Path) -> None:
    """Start every party; stop them all on Ctrl-C or when one exits."""
    prepare(demo_dir)
    # Stop the children on SIGTERM too, not only on Ctrl-C.
    signal.signal(signal.SIGTERM, signal.default_int_handler)
    running: list[subprocess.Popen[bytes]] = []
    try:
        for process in plan(demo_dir):
            party = process.name.split()[-1]
            folder = (
                startup_dir(demo_dir)
                if party == "superlink"
                else hospital_dir(demo_dir, party)
            )
            output = (folder / f"{process.name.split()[0]}.out").open("wb")
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
