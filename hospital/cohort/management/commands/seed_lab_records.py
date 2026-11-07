"""Seed the hospital's lab records (DS1) from a CSV prepare wrote
(ml.dataset.participants), once; with --provide, the laboratory director
then provides the training cohort, as on the Training cohort page."""

from pathlib import Path
from typing import Any

import pandas as pd
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction
from django.utils import timezone

from hospital.cohort.models import LabRecord, TrainingCohort
from ml.cohort import CBC_VARS
from shared.accounts.models import User
from shared.accounts.roles import Role
from shared.vocabulary import RegisteredSex


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--csv", type=Path, required=True)
        parser.add_argument(
            "--provide",
            action="store_true",
            help="the laboratory director provides the training cohort",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        with transaction.atomic():
            if not LabRecord.objects.exists():
                records = pd.read_csv(options["csv"])
                LabRecord.objects.bulk_create(
                    LabRecord(
                        registered_sex=RegisteredSex.of_nhanes(str(row["sex"])),
                        age=int(row["age"]),
                        cbc={
                            var: float(row[var])
                            for var in CBC_VARS
                            if not pd.isna(row[var])
                        },
                        ferritin=None
                        if pd.isna(row["LBXFER"])
                        else float(row["LBXFER"]),
                    )
                    for row in records.to_dict("records")
                )
        self.stdout.write(f"{LabRecord.objects.count()} lab records")
        if options["provide"]:
            self.provide()

    def provide(self) -> None:
        director = User.objects.filter(role=Role.LABORATORY_DIRECTOR).first()
        if director is None or settings.TRAINING_COHORT_DIR is None:
            raise CommandError(
                "Providing needs the laboratory director (seed_hospital) and"
                " TRAINING_COHORT_DIR."
            )
        try:
            TrainingCohort.objects.provide(
                directory=settings.TRAINING_COHORT_DIR, by=director, now=timezone.now()
            )
        except ValidationError as error:
            # Provided on an earlier run of prepare: nothing to do.
            if [refusal.code for refusal in error.error_list] != ["unchanged"]:
                raise CommandError(" ".join(error.messages)) from error
        self.stdout.write("Training cohort provided")
