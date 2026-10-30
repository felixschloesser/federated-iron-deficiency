"""Create the hospital's demo accounts and its analyser stand-in's NHANES values."""

from collections.abc import Hashable
from typing import Any

import pandas as pd

from iron_deficiency.dataset import CBC_VARS
from web.accounts.demo import SeedCommand, user
from web.deployment.models import LaboratoryDirector
from web.lab.models import LaboratoryStaffMember
from web.nhanes.models import Participant


class Command(SeedCommand):
    help = __doc__

    def seed(self, rows: list[dict[Hashable, Any]]) -> list[str]:
        LaboratoryStaffMember.objects.get_or_create(
            user=user("lab-1"), defaults={"name": "Laboratory Staff 1"}
        )
        LaboratoryDirector.objects.get_or_create(
            user=user("director-1"), defaults={"name": "Laboratory Director 1"}
        )
        for row in rows:
            # What this patient's tube would measure.
            ferritin = row["LBXFER"]
            Participant.objects.get_or_create(
                seqn=int(row["sample_id"]),
                defaults={
                    "cbc": {var: float(row[var]) for var in CBC_VARS},
                    "ferritin": None if pd.isna(ferritin) else float(ferritin),
                },
            )
        return ["lab-1", "director-1"]
