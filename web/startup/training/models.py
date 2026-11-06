"""The startup's record of each final model its data scientist transmitted to
the hospitals (features/startup/training.feature)."""

from datetime import datetime
from typing import TYPE_CHECKING

from django.conf import settings
from django.db import models, transaction

from web.startup.training.runs import submit_run

if TYPE_CHECKING:
    from web.accounts.models import User


class TransmissionManager(models.Manager["Transmission"]):
    @transaction.atomic
    def transmit(
        self, *, final_model: str, transmitted_by: "User", now: datetime
    ) -> "Transmission":
        """Submit the run that transmits a final model to every connected hospital,
        and record who did. The run is submitted first: its ID is what the record
        holds, and a refused submission records nothing."""
        run_id = submit_run({"transmit-final-model": final_model})
        return self.create(
            final_model=final_model,
            run_id=str(run_id),
            transmitted_by=transmitted_by,
            submitted_at=now,
        )


class Transmission(models.Model):
    """A run that transmits a final model the startup kept to every hospital."""

    # The training run whose final model it transmits.
    final_model = models.CharField(max_length=64)
    # The Flower run that transmits it.
    run_id = models.CharField(max_length=64, unique=True)
    transmitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    submitted_at = models.DateTimeField()

    objects = TransmissionManager()

    def __str__(self) -> str:
        return f"Run {self.run_id} transmits final model {self.final_model}"
