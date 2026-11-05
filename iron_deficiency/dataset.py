"""NHANES cohort construction from the merged NHANES dataset on Hugging Face."""

from pathlib import Path

import datasets
import pandas as pd
from flwr_datasets import FederatedDataset
from flwr_datasets.partitioner import NaturalIdPartitioner

from iron_deficiency.cohort import CBC_VARS, FEATURES, FERRITIN_THRESHOLD, eligible

# NHANES merged into one row per participant and cycle, pinned to a fixed revision.
HF_DATASET = "gracemyu/nhanes-merged"
HF_REVISION = "2069b6643803fdf1a110b3c632dfc0fe3bb0b08d"
HF_DATA_FILE = "merged_deduped.parquet"

# One NHANES cycle per hospital, keyed by the cycle's first survey year:
# UZ Leuven (large), Heilig Hart Leuven (medium), AZ Diest (small).
CYCLES = {
    "2005-2006": 2005,
    "2015-2016": 2015,
    "2017-2018": 2017,
}
# The cycles are similar in size, so the medium and small hospitals keep a
# fixed sample, giving roughly a 5:2:1 size ratio.
SAMPLE_FRACTIONS = {"2015-2016": 0.5, "2017-2018": 0.25}
# Each cycle's hospital, named as in the report.
HOSPITALS = {
    "2005-2006": "UZ Leuven",
    "2015-2016": "Heilig Hart Leuven",
    "2017-2018": "AZ Diest",
}


def hospital_slug(name: str) -> str:
    """The hospital's folder name under the demo directory (demo/README.md)."""
    return name.lower().replace(" ", "-")


# No hospital trains on the latest cycle, 2021–2023, so it stands in for new
# routine blood counts (all sexes and ages) screened after training.
NEW_SAMPLES_YEAR = 2021

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
        & eligible(merged["RIAGENDR"], merged["RIDAGEYR"])
    ]
    # SEQN order matches the CDC files and increases across cycles.
    cohort = cohort.dropna(subset=FEATURES + ["LBXFER"]).sort_values("SEQN")
    cohort = cohort.assign(
        iron_deficient=(cohort["LBXFER"] < FERRITIN_THRESHOLD).astype(int),
        cycle=cohort["YEAR"].map({year: name for name, year in CYCLES.items()}),
    )
    cohort = pd.concat(
        [
            group.sample(frac=SAMPLE_FRACTIONS.get(str(cycle), 1.0), random_state=0)
            for cycle, group in cohort.groupby("cycle")
        ]
    ).sort_values("SEQN")
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


def _load_new_cycle() -> pd.DataFrame:
    """Return every participant of the 2021–2023 cycle, which no hospital trains on."""
    merged = (
        datasets.load_dataset(
            HF_DATASET,
            revision=HF_REVISION,
            data_files=HF_DATA_FILE,
            columns=list(HF_COLUMNS),
            split="train",
        )
        .to_pandas()
        .rename(columns=HF_COLUMNS)
    )
    return merged[merged["YEAR"] == NEW_SAMPLES_YEAR]


def load_new_samples() -> pd.DataFrame:
    """Return the 2021–2023 cycle as a lab export of new blood counts."""
    samples = _load_new_cycle().dropna(subset=CBC_VARS + ["RIDAGEYR"])
    # The NHANES respondent number stands in for the lab's sample ID.
    return pd.DataFrame(
        {
            "sample_id": samples["SEQN"].astype(int),
            "sex": samples["RIAGENDR"],
            "age": samples["RIDAGEYR"],
            **{var: samples[var] for var in CBC_VARS},
        }
    )


def load_ferritin() -> pd.DataFrame:
    """Return the ferritin results of the new samples, keyed by sample ID.

    Kept apart from load_new_samples: the screening never sees ferritin.
    """
    ferritin = _load_new_cycle()[["SEQN", "LBXFER"]]
    return ferritin.rename(columns={"SEQN": "sample_id"})


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Save one cohort partition per cycle and new samples to screen."
    )
    parser.add_argument("--out-dir", type=Path, default=Path("demo_data"))
    args = parser.parse_args()

    fds = load_federated_dataset()
    partitioner = fds.partitioners["train"]
    if not isinstance(partitioner, NaturalIdPartitioner):
        raise TypeError("The cohort must be partitioned by cycle")
    for partition_id in range(len(CYCLES)):
        partition = fds.load_partition(partition_id)
        cycle = partitioner.partition_id_to_natural_id[partition_id]
        partition.save_to_disk(args.out_dir / cycle)
        print(f"Saved partition {partition_id} ({cycle}) to {args.out_dir / cycle}")

    load_new_samples().to_csv(args.out_dir / "new_samples.csv", index=False)
    print(f"Saved new samples to screen to {args.out_dir / 'new_samples.csv'}")
