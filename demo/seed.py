"""Seed one party's web app for the demo, inside that party's Django:

    python -m demo.seed hospital|practice [--seed N] [--nhanes CSV] [--patients N]
    python -m demo.seed startup
    python -m demo.seed lab-records --csv CSV [--provide]   # the hospital's

DATA_DIR names the party's folder, as for its web app. Its accounts share a
known password, so it runs only with DJANGO_DEBUG=1."""

import argparse
import os
import sys
from pathlib import Path

import django
import pandas as pd
from django.conf import settings

from demo.seeding import participants
from demo.seeding.accounts import PASSWORD

# Whose settings each target runs in.
PARTIES = {
    "hospital": "hospital",
    "practice": "practice",
    "startup": "startup",
    "lab-records": "hospital",
}


def parser() -> argparse.ArgumentParser:
    arguments = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    arguments.add_argument("target", choices=PARTIES)
    arguments.add_argument(
        "--seed", type=int, default=0, help="other patients for each hospital"
    )
    arguments.add_argument(
        "--nhanes", type=Path, help="a CSV of load_nhanes() instead of the network"
    )
    arguments.add_argument(
        "--patients",
        type=int,
        default=participants.PATIENTS,
        help="how many participants; the practice and its hospital need the same",
    )
    arguments.add_argument("--csv", type=Path, help="lab-records: prepare's CSV")
    arguments.add_argument(
        "--provide",
        action="store_true",
        help="lab-records: the laboratory director provides the training cohort",
    )
    return arguments


def chosen_rows(options: argparse.Namespace) -> list[dict[object, object]]:
    nhanes = (
        pd.read_csv(options.nhanes) if options.nhanes else participants.load_nhanes()
    )
    chosen = participants.choose(nhanes, seed=options.seed, patients=options.patients)
    rows: list[dict[object, object]] = participants.with_made_up_ferritin(
        chosen, nhanes
    ).to_dict("records")
    return rows


def main(argv: list[str] | None = None) -> str:
    """Seed the target; what it seeded, in one line."""
    options = parser().parse_args(argv)
    os.environ.setdefault(
        "DJANGO_SETTINGS_MODULE", f"{PARTIES[options.target]}.settings"
    )
    django.setup()
    if not settings.DEBUG:
        raise SystemExit(
            "Demo accounts share a known password; run with DJANGO_DEBUG=1."
        )
    from demo.seeding import parties

    if options.target == "lab-records":
        if options.csv is None:
            raise SystemExit("lab-records needs --csv.")
        return parties.seed_lab_records(options.csv, options.provide)
    if options.target == "startup":
        accounts = parties.seed_startup()
        return f"Accounts {', '.join(accounts)} and no-role, password {PASSWORD}"
    rows = chosen_rows(options)
    seed = (
        parties.seed_hospital if options.target == "hospital" else parties.seed_practice
    )
    accounts = seed(rows)
    return (
        f"Accounts {', '.join(accounts)} and no-role, password {PASSWORD};"
        f" {len(rows)} NHANES participants"
    )


if __name__ == "__main__":
    print(main(sys.argv[1:]))
