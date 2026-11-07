"""The training cohort as files: the hospital writes it when its laboratory
director provides it, the startup's code at the hospital (the ClientApp) reads
it (features/hospital/training_cohort.feature, features/training_cohort_in_runs.feature).

A folder holds at most one training cohort, in a folder named after its
SHA-256; none once withdrawn. Flower is not imported here, so the hospital's
web app can write what the ClientApp reads; Hugging Face's datasets only when
one is written or read, so Django boots without it (tests/demo/test_images.py)."""

import hashlib
import shutil
from pathlib import Path

import pandas as pd


class TrainingCohortUnavailable(RuntimeError):
    """The ClientApp has no training cohort to read this round."""


def sha256(rows: pd.DataFrame) -> str:
    """The cohort's SHA-256: of its rows as CSV, so the same rows hash the same."""
    return hashlib.sha256(rows.to_csv(index=False).encode()).hexdigest()


def training_cohorts(directory: Path) -> list[Path]:
    """The training cohorts in `directory`; a dot folder is one still being written."""
    if not directory.is_dir():
        return []
    return [
        path
        for path in directory.iterdir()
        if path.is_dir() and not path.name.startswith(".")
    ]


def write_training_cohort(rows: pd.DataFrame, directory: Path) -> str:
    """Make `rows` the training cohort in `directory`, in place of any other,
    and return its SHA-256. Written beside, then renamed: a reader never sees
    half a cohort."""
    from datasets import Dataset

    digest = sha256(rows)
    directory.mkdir(parents=True, exist_ok=True)
    staging = directory / f".{digest}"
    shutil.rmtree(staging, ignore_errors=True)
    Dataset.from_pandas(rows, preserve_index=False).save_to_disk(str(staging))
    staging.rename(directory / digest)
    remove_training_cohort(directory, keep=digest)
    return digest


def remove_training_cohort(directory: Path, keep: str | None = None) -> None:
    """Remove every training cohort in `directory` but `keep`."""
    for path in training_cohorts(directory):
        if path.name != keep:
            shutil.rmtree(path)


def read_training_cohort(
    directory: Path, noted: str | None
) -> tuple[str, pd.DataFrame]:
    """The training cohort in `directory` and its SHA-256. `noted` is the one a
    run read in an earlier round: a run trains on one training cohort, so a
    withdrawn or replaced one fails the round instead."""
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
    from datasets import load_from_disk

    (training_cohort,) = found
    return training_cohort.name, load_from_disk(str(training_cohort)).to_pandas()
