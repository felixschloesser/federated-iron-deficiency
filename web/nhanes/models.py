"""The analyser's stand-in: what each demo patient's blood would measure."""

from typing import assert_never

from django.db import models

from web.vocabulary import Test

FERRITIN = "LBXFER"  # NHANES variable name, as the CBC keys (CBC_VARS)
# A demo value where NHANES has none; reported under its own name, never as ferritin.
MADE_UP_FERRITIN = "MADE_UP_LBXFER"


class Participant(models.Model):
    seqn = models.PositiveIntegerField(unique=True)
    # The 13 CBC values keyed by NHANES variable name (iron_deficiency.cohort.CBC_VARS).
    cbc = models.JSONField()
    # NHANES measured ferritin for only some participants (spec §8).
    ferritin = models.FloatField(null=True, blank=True)
    # Made up for the demo where NHANES has no ferritin (web.seeding.command).
    made_up_ferritin = models.FloatField(null=True, blank=True)

    def __str__(self) -> str:
        return f"NHANES {self.seqn}"

    def measure(self, test: Test) -> dict[str, float]:
        """What the analyser reads for this test: NHANES's ferritin, else the made-up
        one under its own name, else nothing."""
        match test:
            case Test.CBC:
                return dict(self.cbc)
            case Test.FERRITIN:
                if self.ferritin is not None:
                    return {FERRITIN: self.ferritin}
                if self.made_up_ferritin is not None:
                    return {MADE_UP_FERRITIN: self.made_up_ferritin}
                return {}
            case _:
                assert_never(test)
