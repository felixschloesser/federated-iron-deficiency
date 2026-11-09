"""Seed one party's web app for the demo, inside that party's Django, from the
NHANES extract nhanes-download wrote for it (demo/nhanes.py):

    python -m demo.seed hospital --rows PARTICIPANTS --lab-records CSV [--provide]
    python -m demo.seed practice --sample-ids CSV --patients CSV
    python -m demo.seed startup

DATA_DIR names the party's folder, as for its web app. Its accounts share a
known password, so it runs only with DJANGO_DEBUG=1."""

import argparse
import os
import sys
from pathlib import Path

import django
from django.conf import settings

from demo.seeding.accounts import PASSWORD


def parser() -> argparse.ArgumentParser:
    arguments = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parties = arguments.add_subparsers(dest="party", required=True)
    hospital = parties.add_parser("hospital")
    hospital.add_argument(
        "--rows", type=Path, required=True, help="its participants.csv"
    )
    hospital.add_argument(
        "--lab-records", type=Path, required=True, help="its lab-records.csv"
    )
    hospital.add_argument(
        "--provide",
        action="store_true",
        help="the laboratory director provides the training cohort",
    )
    practice = parties.add_parser("practice")
    practice.add_argument(
        "--sample-ids", type=Path, required=True, help="its sample-ids.csv"
    )
    practice.add_argument(
        "--patients", type=Path, required=True, help="its patients.csv"
    )
    parties.add_parser("startup")
    return arguments


def main(argv: list[str] | None = None) -> str:
    """Seed the party; what it seeded, in one line."""
    options = parser().parse_args(argv)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", f"web.{options.party}.settings")
    django.setup()
    if not settings.DEBUG:
        raise SystemExit(
            "Demo accounts share a known password; run with DJANGO_DEBUG=1."
        )
    from demo.seeding import parties

    if options.party == "startup":
        accounts = parties.seed_startup()
        return f"Accounts {', '.join(accounts)} and no-role, password {PASSWORD}"
    if options.party == "hospital":
        rows = parties.read_rows(options.rows)
        accounts = parties.seed_hospital(rows)
        records = parties.seed_lab_records(options.lab_records, options.provide)
        seeded = f"{len(rows)} NHANES participants, {records}"
    else:
        sample_ids = parties.read_rows(options.sample_ids)
        patients = parties.read_rows(options.patients)
        accounts = parties.seed_practice(sample_ids, patients)
        seeded = f"{len(sample_ids)} sample IDs, {len(patients)} patients"
    return f"Accounts {', '.join(accounts)} and no-role, password {PASSWORD}; {seeded}"


if __name__ == "__main__":
    print(main(sys.argv[1:]))
