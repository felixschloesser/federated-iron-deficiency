"""NHANES cohort construction from the merged NHANES dataset on Hugging Face."""

from pathlib import Path

import datasets
import pandas as pd
from flwr_datasets import FederatedDataset
from flwr_datasets.partitioner import NaturalIdPartitioner

# NHANES merged into one row per participant and cycle, pinned to a fixed revision.
HF_DATASET = "gracemyu/nhanes-merged"
HF_REVISION = "2069b6643803fdf1a110b3c632dfc0fe3bb0b08d"
HF_DATA_FILE = "merged_deduped.parquet"

# One NHANES cycle per partition, keyed by the cycle's first survey year.
CYCLES = {
    "2005-2006": 2005,
    "2015-2016": 2015,
    "2017-2018": 2017,
    "2021-2023": 2021,
}

CBC_VARS = [
    "LBXWBCSI",
    "LBXRBCSI",
    "LBXHGB",
    "LBXHCT",
    "LBXMCVSI",
    "LBXMC",
    "LBXMCHSI",
    "LBXRDW",
    "LBXPLTSI",
    "LBXMPSI",
    "LBDLYMNO",
    "LBDNENO",
    "LBDMONO",
]
FEATURES = CBC_VARS + ["RIDAGEYR"]
FERRITIN_THRESHOLD = 15.0

# Merged columns are named `{source_table}_{variable}` in lowercase.
HF_COLUMNS = {
    "seqn": "SEQN",
    "year": "YEAR",
    "demo_riagendr": "RIAGENDR",
    "demo_ridageyr": "RIDAGEYR",
    **{f"cbc_{var.lower()}": var for var in CBC_VARS},
    "fertin_lbxfer": "LBXFER",
}


def build_cohort(dataset_dict: datasets.DatasetDict) -> datasets.DatasetDict:
    """Reduce the merged NHANES table to the notebook cohort of each cycle."""
    merged = dataset_dict["train"].to_pandas().rename(columns=HF_COLUMNS)
    cohort = merged[
        merged["YEAR"].isin(CYCLES.values())
        & (merged["RIAGENDR"] == "Female")
        & merged["RIDAGEYR"].between(18, 49)
    ]
    # SEQN order matches the CDC files and increases across cycles.
    cohort = cohort.dropna(subset=FEATURES + ["LBXFER"]).sort_values("SEQN")
    cohort = cohort.assign(
        iron_deficient=(cohort["LBXFER"] < FERRITIN_THRESHOLD).astype(int),
        cycle=cohort["YEAR"].map({year: name for name, year in CYCLES.items()}),
    )
    columns = FEATURES + ["iron_deficient", "cycle"]
    return datasets.DatasetDict(
        {"train": datasets.Dataset.from_pandas(cohort[columns], preserve_index=False)}
    )


def load_federated_dataset() -> FederatedDataset:
    """Return the cohort partitioned by cycle; partition IDs follow `CYCLES` order."""
    return FederatedDataset(
        dataset=HF_DATASET,
        revision=HF_REVISION,
        data_files=HF_DATA_FILE,
        columns=list(HF_COLUMNS),
        preprocessor=build_cohort,
        partitioners={"train": NaturalIdPartitioner(partition_by="cycle")},
        shuffle=False,  # Keep SEQN order so splits are reproducible
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Save one NHANES cohort partition per cycle for SuperNodes."
    )
    parser.add_argument("--out-dir", type=Path, default=Path("demo_data"))
    args = parser.parse_args()

    fds = load_federated_dataset()
    partitioner = fds.partitioners["train"]
    for partition_id in range(len(CYCLES)):
        partition = fds.load_partition(partition_id)
        cycle = partitioner.partition_id_to_natural_id[partition_id]
        partition.save_to_disk(args.out_dir / cycle)
        print(f"Saved partition {partition_id} ({cycle}) to {args.out_dir / cycle}")
