"""The training cohort as files on disk (features/hospital/training_cohort.feature).

The hospital's web app writes the training cohort when the laboratory director
provides it; the ClientApp, the startup's code running at the hospital, reads
it. A folder holds at most one training cohort, in a subfolder named after its
SHA-256, and none once it is withdrawn. This module does not import Flower, so
the hospital's web app can write the one Parquet file the ClientApp reads using
only pandas."""

import hashlib
import shutil
from pathlib import Path

import pandas as pd

# The one file in a training cohort's folder.
COHORT_FILE = "cohort.parquet"


class TrainingCohortUnavailable(RuntimeError):
    """Raised when the ClientApp has no usable training cohort this round."""


def sha256(rows: pd.DataFrame) -> str:
    """The cohort's SHA-256, taken over its rows as CSV, so the same rows always
    give the same hash."""
    return hashlib.sha256(rows.to_csv(index=False).encode()).hexdigest()


def training_cohorts(directory: Path) -> list[Path]:
    """The training cohorts in `directory`. A folder whose name starts with a dot
    is still being written and is skipped."""
    if not directory.is_dir():
        return []
    return [
        path
        for path in directory.iterdir()
        if path.is_dir() and not path.name.startswith(".")
    ]


def write_training_cohort(rows: pd.DataFrame, directory: Path) -> str:
    """Make `rows` the only training cohort in `directory` and return its SHA-256.
    The cohort is written to a dot folder first and then renamed, so a reader
    never sees half a cohort."""
    digest = sha256(rows)
    directory.mkdir(parents=True, exist_ok=True)
    staging = directory / f".{digest}"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir()
    rows.to_parquet(staging / COHORT_FILE, index=False)
    staging.rename(directory / digest)
    remove_training_cohort(directory, keep=digest)
    return digest


def remove_training_cohort(directory: Path, keep: str | None = None) -> None:
    """Remove every training cohort in `directory` except `keep`."""
    for path in training_cohorts(directory):
        if path.name != keep:
            shutil.rmtree(path)


def read_training_cohort(
    directory: Path, noted: str | None
) -> tuple[str, pd.DataFrame]:
    """The training cohort in `directory` and its SHA-256.

    `noted` is the SHA-256 the run read in an earlier round, or None in its
    first round. A run must train on one training cohort throughout, so if the
    cohort was withdrawn or replaced since, the round fails."""
    found = training_cohorts(directory)
    if not found:
        raise TrainingCohortUnavailable(
            "This hospital has no training cohort: its laboratory director has"
            " not provided one, or withdrew it."
        )
    if len(found) > 1 or (noted is not None and found[0].name != noted):
        raise TrainingCohortUnavailable(
            "The training cohort changed during this run: the laboratory director"
            " provided another."
        )
    (training_cohort,) = found
    return training_cohort.name, pd.read_parquet(training_cohort / COHORT_FILE)
