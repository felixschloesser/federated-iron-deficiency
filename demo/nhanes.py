"""nhanes-download: write the public NHANES extracts each party seeds from.

    python -m demo.nhanes --out-dir DIR --pair CYCLE HOSPITAL PRACTICE PATIENTS ...

It writes one folder per party (demo/README.md). It runs in the only demo
container that reaches the internet, and that container mounts no party's volume.

Each --pair names a hospital and the practice that shares its NHANES cycle, by
folder name, and how many patients the practice seeds. demo/compose.yaml passes
the pairs, so this script holds no list of parties and its image needs no
rebuild when the demo's parties change.

A hospital's folder holds its past lab records (its share of its cycle) and the
participants its analyser stand-in measures; that pool is the same at every
hospital. A practice's folder holds its stock of sample IDs, drawn from the
pool, and its patients (demo/seeding/participants.py).

Extracts already written are kept: a later run that finds them, written by the
same code for the same pairs, touches neither the network nor the files.
"""

import argparse
import hashlib
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from demo.seeding.participants import patients, pool, stock
from ml import dataset

ROOT = Path(__file__).resolve().parents[1]
# The files that decide the extracts' contents. When any of them changes, the
# extracts are written again, from huggingface_hub's cache, so nothing is
# downloaded twice.
SOURCES = (
    "ml/cohort.py",
    "ml/dataset.py",
    "demo/nhanes.py",
    "demo/seeding/participants.py",
)
FINGERPRINT = "fingerprint"


@dataclass(frozen=True)
class Pair:
    """A hospital and the practice that shares its NHANES cycle, by folder name;
    the practice seeds `patients` of the 2021-2023 participants."""

    cycle: str
    hospital: str
    practice: str
    patients: int


def fingerprint(pairs: list[Pair]) -> str:
    digest = hashlib.sha256(repr(pairs).encode())
    for source in SOURCES:
        digest.update((ROOT / source).read_bytes())
    return digest.hexdigest()


def expected(pairs: list[Pair]) -> list[Path]:
    """Every extract's path, relative to the output folder."""
    files = []
    for pair in pairs:
        files += [
            Path(pair.hospital, "lab-records.csv"),
            Path(pair.hospital, "participants.csv"),
            Path(pair.practice, "sample-ids.csv"),
            Path(pair.practice, "patients.csv"),
        ]
    return files


def extracts(
    pairs: list[Pair],
    lab_records: Callable[[str], pd.DataFrame],
    nhanes: pd.DataFrame,
) -> dict[Path, pd.DataFrame]:
    """Each extract's rows. `lab_records` gives a cycle's share of participants;
    `nhanes` holds the 2021-2023 participants that practices and analysers seed
    from. Each practice's draws are seeded with its pair's position in `pairs`,
    so the same pairs always give the same draws."""
    # Any practice may send a sample to any hospital, so every hospital holds the
    # whole pool.
    participants = pool(nhanes)
    files: dict[Path, pd.DataFrame] = {}
    for partition, pair in enumerate(pairs):
        files[Path(pair.hospital, "lab-records.csv")] = lab_records(pair.cycle)
        files[Path(pair.hospital, "participants.csv")] = participants
        # The practice holds no blood values.
        files[Path(pair.practice, "sample-ids.csv")] = stock(
            nhanes, seed=partition, patients=pair.patients
        )
        files[Path(pair.practice, "patients.csv")] = patients(
            nhanes, seed=partition, count=pair.patients
        )
    return files


def from_hub[T](load: Callable[[], T], attempts: int = 4) -> T:
    """Call `load`, retrying with longer waits when Hugging Face refuses, as it
    does when unauthenticated downloads hit its rate limit."""
    for attempt in range(1, attempts):
        try:
            return load()
        except (ValueError, ConnectionError):
            print(
                f"Hugging Face refused; retrying in {15 * attempt} s", file=sys.stderr
            )
            time.sleep(15 * attempt)
    return load()


def nhanes_2021_2023() -> pd.DataFrame:
    """The 2021-2023 participants with their ferritin and CRP."""
    return dataset.new_cycle_participants().merge(
        dataset.new_cycle_ferritin_and_crp(), on="sample_id", how="left"
    )


def download(out_dir: Path, pairs: list[Pair]) -> bool:
    """Write every extract into `out_dir`, unless the same code already wrote them
    for the same pairs. Returns whether it wrote them."""
    stamp = out_dir / FINGERPRINT
    current = fingerprint(pairs)
    if (
        stamp.exists()
        and stamp.read_text() == current
        and all((out_dir / path).exists() for path in expected(pairs))
    ):
        return False
    files = extracts(
        pairs,
        lambda cycle: from_hub(lambda: dataset.participants(cycle)),
        from_hub(nhanes_2021_2023),
    )
    for path, rows in files.items():
        target = out_dir / path
        target.parent.mkdir(parents=True, exist_ok=True)
        # Write to a partial file, then rename it, so an interrupted run leaves no
        # half-written file.
        partial = target.with_name(f".{target.name}.partial")
        rows.to_csv(partial, index=False)
        partial.rename(target)
    stamp.write_text(current)
    return True


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument(
        "--pair",
        nargs=4,
        action="append",
        required=True,
        metavar=("CYCLE", "HOSPITAL", "PRACTICE", "PATIENTS"),
    )
    options = parser.parse_args(argv)
    pairs = [
        Pair(cycle, hospital, practice, int(patients))
        for cycle, hospital, practice, patients in options.pair
    ]
    if download(options.out_dir, pairs):
        print(f"NHANES extracts written to {options.out_dir}.")
    else:
        print("NHANES extracts up to date.")


if __name__ == "__main__":
    main()
