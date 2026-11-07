"""nhanes-download: the public NHANES extracts each party seeds from, one folder
per party (demo/README.md). The one container that reaches the internet runs
it, and it sees no party's volume.

    python -m demo.nhanes --out-dir DIR --pair CYCLE HOSPITAL PRACTICE PATIENTS ...

Each --pair is a hospital and the practice of its cycle, by folder name, and
how many patients the practice seeds; compose passes them (demo/topology.py),
so this needs no topology and its image no rebuild when the demo's parties
change.

A hospital's folder holds its past lab records (its cycle's share) and the
participants its analyser stand-in measures; a practice's folder holds its
patients. Each practice's patients are drawn as the seed commands draw them, so
a hospital's analyser holds a tube for every practice's patients.

Once written, the extracts are kept: a later run that finds them, made by the
same code, touches neither the network nor the files.
"""

import argparse
import hashlib
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from demo.seeding.participants import choose, with_made_up_ferritin
from ml import dataset

ROOT = Path(__file__).resolve().parents[1]
# What decides the extracts' contents: a change to any makes them again (from
# huggingface_hub's cache, so without downloading twice).
SOURCES = (
    "ml/cohort.py",
    "ml/dataset.py",
    "demo/nhanes.py",
    "demo/seeding/participants.py",
)
FINGERPRINT = "fingerprint"


@dataclass(frozen=True)
class Pair:
    """A hospital and the practice of its NHANES cycle, by folder name; the
    practice seeds `patients` of the 2021-2023 participants."""

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
    """Every extract, relative to the output folder."""
    files = []
    for pair in pairs:
        files += [
            Path(pair.hospital, "lab-records.csv"),
            Path(pair.hospital, "participants.csv"),
            Path(pair.practice, "patients.csv"),
        ]
    return files


def extracts(
    pairs: list[Pair],
    lab_records: Callable[[str], pd.DataFrame],
    nhanes: pd.DataFrame,
) -> dict[Path, pd.DataFrame]:
    """Each extract's rows: `lab_records` gives a cycle's share of participants,
    `nhanes` the 2021-2023 participants practices and analysers seed from. The
    pairs' order numbers the practices' draws, as the seed commands number them."""
    patients = {
        pair.practice: with_made_up_ferritin(
            choose(nhanes, seed=partition, patients=pair.patients), nhanes
        )
        for partition, pair in enumerate(pairs)
    }
    # Any practice may send a sample to any hospital.
    every_patient = pd.concat(patients.values()).drop_duplicates("sample_id")
    files: dict[Path, pd.DataFrame] = {}
    for pair in pairs:
        files[Path(pair.hospital, "lab-records.csv")] = lab_records(pair.cycle)
        files[Path(pair.hospital, "participants.csv")] = every_patient
        files[Path(pair.practice, "patients.csv")] = patients[pair.practice]
    return files


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


def nhanes_2021_2023() -> pd.DataFrame:
    """The 2021-2023 participants with their ferritin and CRP."""
    return dataset.new_cycle_participants().merge(
        dataset.new_cycle_ferritin_and_crp(), on="sample_id", how="left"
    )


def download(out_dir: Path, pairs: list[Pair]) -> bool:
    """Write every extract into `out_dir`, unless the same code already did for
    the same pairs; whether it wrote them."""
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
        # Written beside, then renamed: an interrupted run leaves no half file.
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
