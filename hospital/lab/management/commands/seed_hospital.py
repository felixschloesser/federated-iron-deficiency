"""Create the hospital's demo accounts and its analyser stand-in's NHANES values."""

from collections.abc import Hashable
from typing import Any

import pandas as pd

from hospital.nhanes.models import Participant
from ml.cohort import CBC_VARS
from shared.accounts.roles import Role
from shared.seeding.accounts import LABORATORY_DIRECTOR, LABORATORY_STAFF
from shared.seeding.command import SeedCommand, user


class Command(SeedCommand):
    help = __doc__

    def seed(self, rows: list[dict[Hashable, Any]]) -> list[str]:
        user(LABORATORY_STAFF, Role.LABORATORY_STAFF)
        user(LABORATORY_DIRECTOR, Role.LABORATORY_DIRECTOR)
        for row in rows:
            # What this patient's tube would measure.
            ferritin, made_up = row["LBXFER"], row["made_up_ferritin"]
            Participant.objects.get_or_create(
                seqn=int(row["sample_id"]),
                defaults={
                    "cbc": {var: float(row[var]) for var in CBC_VARS},
                    "ferritin": None if pd.isna(ferritin) else float(ferritin),
                    "made_up_ferritin": None if pd.isna(made_up) else float(made_up),
                },
            )
        return [LABORATORY_STAFF, LABORATORY_DIRECTOR]
