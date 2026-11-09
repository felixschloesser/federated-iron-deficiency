"""Build the training cohorts and the demo's data from the merged NHANES dataset
on Hugging Face."""

from pathlib import Path

import pandas as pd

from ml.cohort import CBC_VARS, FEATURES, eligible, iron_deficient

# NHANES merged into one row per participant and cycle, pinned to a fixed revision.
HF_DATASET = "gracemyu/nhanes-merged"
HF_REVISION = "2069b6643803fdf1a110b3c632dfc0fe3bb0b08d"
HF_DATA_FILE = "merged_deduped.parquet"

# Each hospital trains on one NHANES cycle (demo/compose.yaml assigns them). The
# value is the cycle's first survey year.
CYCLES = {
    "2005-2006": 2005,
    "2015-2016": 2015,
    "2017-2018": 2017,
}
# The cycles are about the same size, so the second and third hospitals keep
# only a fixed random sample of theirs. That makes a large, a medium and a small
# hospital, roughly 5:2:1.
CYCLE_FRACTIONS = {"2015-2016": 0.5, "2017-2018": 0.25}
# No hospital trains on the latest cycle, 2021–2023, so the demo uses it for the
# new routine blood counts (any sex and age) that are screened after training.
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
    """Rename the merged table's columns to NHANES's own names and add CRP in mg/L.
    CRP comes from the high-sensitivity assay where a cycle has it (already in
    mg/L), otherwise from the standard assay (in mg/dL, so times 10)."""
    renamed = table.rename(columns=HF_COLUMNS)
    return renamed.assign(CRP=renamed["LBXHSCRP"].fillna(renamed["LBXCRP"] * 10))


def pregnant(participants: pd.DataFrame) -> "pd.Series[bool]":
    """True for each participant pregnant at the exam; NHANES labels a positive
    answer "Yes, …"."""
    return participants["RIDEXPRG"].fillna("").str.startswith("Yes")


def in_cohort(participants: pd.DataFrame) -> "pd.Series[bool]":
    """True for each participant who belongs in the training cohort: eligible,
    not pregnant (a CBC at the start of pregnancy is not screened), and with
    every feature, a ferritin and a CRP."""
    return (
        eligible(participants["RIAGENDR"], participants["RIDAGEYR"])
        & ~pregnant(participants)
        & participants[FEATURES + ["LBXFER", "CRP"]].notna().all(axis=1)
    )


def hospital_share(participants: pd.DataFrame, cycle: str) -> pd.DataFrame:
    """The hospital's fixed random sample of its cycle's participants, in SEQN
    order. The simulation's cohort and the hospital's seeded lab records both
    use this draw, so a training cohort the hospital provides from its lab
    records holds the same rows a simulation trains on."""
    # Sorted before sampling so the draw does not depend on the input's row
    # order. SEQN, NHANES's respondent number, increases across cycles.
    return (
        participants.sort_values("SEQN")
        .sample(frac=CYCLE_FRACTIONS.get(cycle, 1.0), random_state=0)
        .sort_values("SEQN")
    )


def build_cohort(merged: pd.DataFrame) -> pd.DataFrame:
    """Reduce the merged NHANES table to each cycle's labelled training cohort,
    in SEQN order."""
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
    return cohort[columns].reset_index(drop=True)


def _merged() -> pd.DataFrame:
    """Every participant of every cycle, read from the pinned file. huggingface_hub
    caches the file, so it is downloaded only once."""
    from huggingface_hub import hf_hub_download

    path = hf_hub_download(
        HF_DATASET, HF_DATA_FILE, repo_type="dataset", revision=HF_REVISION
    )
    return _renamed(pd.read_parquet(path, columns=list(HF_COLUMNS)))


def cohorts() -> list[pd.DataFrame]:
    """Each cycle's cohort, in `CYCLES` order; a simulation's partition ID indexes
    this list."""
    cohort = build_cohort(_merged())
    return [cohort[cohort["cycle"] == cycle].reset_index(drop=True) for cycle in CYCLES]


def _load_cycle(year: int) -> pd.DataFrame:
    """Every participant of the NHANES cycle that starts in `year`."""
    merged = _merged()
    return merged[merged["YEAR"] == year]


def participants(cycle: str) -> pd.DataFrame:
    """The hospital's share of `cycle`'s participants who have every feature,
    which the demo seeds as the hospital's past lab records. Each row has
    ferritin and CRP (mg/L) where NHANES measured them, and whether the
    participant was pregnant; rows are in SEQN order."""
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
    """The 2021–2023 participants with a complete CBC and an age, which the demo
    seeds as new blood counts."""
    samples = _load_cycle(NEW_CYCLE_YEAR).dropna(subset=CBC_VARS + ["RIDAGEYR"])
    # The NHANES respondent number stands in for the laboratory's sample ID.
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
    Kept apart from new_cycle_participants because the screening must never see
    them."""
    iron = _load_cycle(NEW_CYCLE_YEAR)[["SEQN", "LBXFER", "CRP"]]
    return iron.rename(columns={"SEQN": "sample_id"})


if __name__ == "__main__":
    import argparse

    from ml.training_cohort import write_training_cohort

    parser = argparse.ArgumentParser(
        description="Save each cycle's cohort as the training cohort a SuperNode's"
        " data-path reads."
    )
    parser.add_argument("--out-dir", type=Path, default=Path("demo_data"))
    args = parser.parse_args()

    for partition_id, (cycle, rows) in enumerate(zip(CYCLES, cohorts(), strict=True)):
        write_training_cohort(rows[FEATURES + ["iron_deficient"]], args.out_dir / cycle)
        print(f"Saved partition {partition_id} ({cycle}) to {args.out_dir / cycle}")
