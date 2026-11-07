"""NHANES cohort construction from the merged NHANES dataset on Hugging Face."""

from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

from ml.cohort import CBC_VARS, FEATURES, eligible, iron_deficient

# The simulation's libraries, imported where it loads its data: the demo's
# extracts need only pandas (demo/nhanes-download.Dockerfile).
if TYPE_CHECKING:
    import datasets
    from flwr_datasets import FederatedDataset

# NHANES merged into one row per participant and cycle, pinned to a fixed revision.
HF_DATASET = "gracemyu/nhanes-merged"
HF_REVISION = "2069b6643803fdf1a110b3c632dfc0fe3bb0b08d"
HF_DATA_FILE = "merged_deduped.parquet"

# One NHANES cycle per hospital (demo/compose.yaml names them), keyed by the
# cycle's first survey year: a large, a medium and a small hospital.
CYCLES = {
    "2005-2006": 2005,
    "2015-2016": 2015,
    "2017-2018": 2017,
}
# The cycles are similar in size, so the medium and small hospitals keep a
# fixed sample, giving roughly a 5:2:1 size ratio.
CYCLE_FRACTIONS = {"2015-2016": 0.5, "2017-2018": 0.25}
# No hospital trains on the latest cycle, 2021–2023, so it stands in for new
# routine blood counts (all sexes and ages) screened after training.
NEW_CYCLE_YEAR = 2021

# Merged columns are named `{source_table}_{variable}` in lowercase.
HF_COLUMNS = {
    "seqn": "SEQN",
    "year": "YEAR",
    "demo_riagendr": "RIAGENDR",
    "demo_ridageyr": "RIDAGEYR",
    "demo_ridexprg": "RIDEXPRG",
    **{f"cbc_{var.lower()}": var for var in CBC_VARS},
    "fertin_lbxfer": "LBXFER",
    "crp_lbxcrp": "LBXCRP",
    "hscrp_lbxhscrp": "LBXHSCRP",
}


def _renamed(table: pd.DataFrame) -> pd.DataFrame:
    """The merged table in NHANES's names, with CRP in mg/L: the high-sensitivity
    assay where a cycle has it (mg/L), else the standard one (mg/dL)."""
    renamed = table.rename(columns=HF_COLUMNS)
    return renamed.assign(CRP=renamed["LBXHSCRP"].fillna(renamed["LBXCRP"] * 10))


def pregnant(participants: pd.DataFrame) -> "pd.Series[bool]":
    """Who was pregnant at the exam; NHANES labels a positive answer "Yes, …"."""
    return participants["RIDEXPRG"].fillna("").str.startswith("Yes")


def in_cohort(participants: pd.DataFrame) -> "pd.Series[bool]":
    """Who of a cycle's participants the cohort holds: eligible, not pregnant
    (a CBC at the start of pregnancy is not screened), with every feature and
    a ferritin."""
    return (
        eligible(participants["RIAGENDR"], participants["RIDAGEYR"])
        & ~pregnant(participants)
        & participants[FEATURES + ["LBXFER", "CRP"]].notna().all(axis=1)
    )


def hospital_share(participants: pd.DataFrame, cycle: str) -> pd.DataFrame:
    """The hospital's fixed sample of its cycle's participants, in SEQN order.
    The one draw both the simulation's cohort and the hospital's past lab
    records take, so a training cohort provided from those holds the rows a
    simulation trains on."""
    # SEQN order matches the CDC files and increases across cycles.
    return (
        participants.sort_values("SEQN")
        .sample(frac=CYCLE_FRACTIONS.get(cycle, 1.0), random_state=0)
        .sort_values("SEQN")
    )


def build_cohort(dataset_dict: "datasets.DatasetDict") -> "datasets.DatasetDict":
    """Reduce the merged NHANES table to the cohort of each cycle."""
    import datasets

    merged = _renamed(dataset_dict["train"].to_pandas())
    cohort = pd.concat(
        [
            hospital_share(
                merged[(merged["YEAR"] == year) & in_cohort(merged)], cycle
            ).assign(cycle=cycle)
            for cycle, year in sorted(CYCLES.items())
        ]
    ).sort_values("SEQN")
    cohort = cohort.assign(
        iron_deficient=iron_deficient(cohort["LBXFER"], cohort["CRP"]).astype(int)
    )
    columns = FEATURES + ["iron_deficient", "cycle"]
    return datasets.DatasetDict(
        {"train": datasets.Dataset.from_pandas(cohort[columns], preserve_index=False)}
    )


def load_federated_dataset() -> "FederatedDataset":
    """Return the cohort partitioned by cycle; partition IDs follow `CYCLES` order."""
    from flwr_datasets import FederatedDataset
    from flwr_datasets.partitioner import NaturalIdPartitioner

    return FederatedDataset(
        dataset=HF_DATASET,
        revision=HF_REVISION,
        data_files=HF_DATA_FILE,
        columns=list(HF_COLUMNS),
        preprocessor=build_cohort,
        partitioners={"train": NaturalIdPartitioner(partition_by="cycle")},
        shuffle=False,  # Keep SEQN order so splits are reproducible
    )


def _load_cycle(year: int) -> pd.DataFrame:
    """Return every participant of the cycle starting in `year`, from the pinned
    file (cached by huggingface_hub, so read from the network once)."""
    from huggingface_hub import hf_hub_download

    path = hf_hub_download(
        HF_DATASET, HF_DATA_FILE, repo_type="dataset", revision=HF_REVISION
    )
    merged = _renamed(pd.read_parquet(path, columns=list(HF_COLUMNS)))
    return merged[merged["YEAR"] == year]


def participants(cycle: str) -> pd.DataFrame:
    """The hospital's share of `cycle`'s participants with every feature, with
    ferritin and CRP (mg/L) where NHANES measured them and whether each was
    pregnant, in SEQN order: what the demo seeds as the hospital's past lab
    records (DS1)."""
    measured = _load_cycle(CYCLES[cycle]).dropna(subset=FEATURES)
    cohort = in_cohort(measured)
    sampled = pd.concat(
        [
            hospital_share(measured[cohort], cycle),
            hospital_share(measured[~cohort], cycle),
        ]
    ).sort_values("SEQN")
    return pd.DataFrame(
        {
            "sex": sampled["RIAGENDR"],
            "age": sampled["RIDAGEYR"].astype(int),
            **{var: sampled[var] for var in CBC_VARS},
            "LBXFER": sampled["LBXFER"],
            "CRP": sampled["CRP"],
            "pregnant": pregnant(sampled),
        }
    )


def new_cycle_participants() -> pd.DataFrame:
    """The 2021–2023 participants with a complete CBC and an age: what the demo
    seeds as new blood counts."""
    samples = _load_cycle(NEW_CYCLE_YEAR).dropna(subset=CBC_VARS + ["RIDAGEYR"])
    # The NHANES respondent number stands in for the lab's sample ID.
    return pd.DataFrame(
        {
            "sample_id": samples["SEQN"].astype(int),
            "sex": samples["RIAGENDR"],
            "age": samples["RIDAGEYR"],
            **{var: samples[var] for var in CBC_VARS},
        }
    )


def new_cycle_ferritin_and_crp() -> pd.DataFrame:
    """The 2021–2023 participants' ferritin and CRP (mg/L), keyed by sample ID.
    Kept apart from new_cycle_participants: the screening never sees either."""
    iron = _load_cycle(NEW_CYCLE_YEAR)[["SEQN", "LBXFER", "CRP"]]
    return iron.rename(columns={"SEQN": "sample_id"})


if __name__ == "__main__":
    import argparse

    from flwr_datasets.partitioner import NaturalIdPartitioner

    from ml.training_cohort import write_training_cohort

    parser = argparse.ArgumentParser(
        description="Save each cycle's cohort as the training cohort a SuperNode's"
        " data-path reads."
    )
    parser.add_argument("--out-dir", type=Path, default=Path("demo_data"))
    args = parser.parse_args()

    fds = load_federated_dataset()
    partitioner = fds.partitioners["train"]
    if not isinstance(partitioner, NaturalIdPartitioner):
        raise TypeError("The cohort must be partitioned by cycle")
    for partition_id in range(len(CYCLES)):
        rows = fds.load_partition(partition_id).to_pandas()
        # Known only once a partition is loaded.
        cycle = partitioner.partition_id_to_natural_id[partition_id]
        write_training_cohort(rows[FEATURES + ["iron_deficient"]], args.out_dir / cycle)
        print(f"Saved partition {partition_id} ({cycle}) to {args.out_dir / cycle}")
