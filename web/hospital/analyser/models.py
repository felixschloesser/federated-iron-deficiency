"""The demo's stand-in for the analyser: the blood values of the NHANES 2021–2023
participants it seeds, women aged 18–49 with a complete CBC and a measured
ferritin."""

from typing import assert_never

from django.db import models

from web.shared.vocabulary import Test

FERRITIN = "LBXFER"  # NHANES variable name, like the CBC keys (CBC_VARS)


class Participant(models.Model):
    seqn = models.PositiveIntegerField(unique=True)
    # The 13 CBC values keyed by NHANES variable name (ml.cohort.CBC_VARS).
    cbc = models.JSONField()
    ferritin = models.FloatField()

    def __str__(self) -> str:
        return f"NHANES {self.seqn}"

    def measure(self, test: Test) -> dict[str, float]:
        """The values the analyser reads for this test."""
        match test:
            case Test.CBC:
                return dict(self.cbc)
            case Test.FERRITIN:
                return {FERRITIN: self.ferritin}
            case _:
                assert_never(test)
