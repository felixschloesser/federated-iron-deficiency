"""The analyser's stand-in: what each demo patient's blood would measure."""

from typing import assert_never

from django.db import models

from web.vocabulary import Test

FERRITIN = "LBXFER"  # NHANES variable name, as the CBC keys (CBC_VARS)


class Participant(models.Model):
    seqn = models.PositiveIntegerField(unique=True)
    # The 13 CBC values keyed by NHANES variable name (iron_deficiency.dataset.CBC_VARS).
    cbc = models.JSONField()
    # NHANES measured ferritin for only some participants (spec §8).
    ferritin = models.FloatField(null=True, blank=True)

    def __str__(self) -> str:
        return f"NHANES {self.seqn}"

    def measure(self, test: Test) -> dict[str, float]:
        """What the analyser reads for this test: empty when NHANES has no value."""
        match test:
            case Test.CBC:
                return dict(self.cbc)
            case Test.FERRITIN:
                return {} if self.ferritin is None else {FERRITIN: self.ferritin}
            case _:
                assert_never(test)
