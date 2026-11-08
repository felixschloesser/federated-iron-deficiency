"""The screening models the laboratory director deployed (features/hospital/deployment.feature)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from django.core.exceptions import ValidationError
from django.db import models, transaction

from ml.final_model import final_model_path
from ml.inference import probability
from web.hospital.deployment.model_files import (
    ScreeningModelFile,
    model_name,
    screening_model_file,
    sha256,
)


class NoUsableModel(models.TextChoices):
    NO_DEPLOYED_MODEL = "no_deployed_model", "No screening model is deployed"
    DEPLOYED_MODEL_CHANGED = (
        "deployed_model_changed",
        "The deployed model changed on disk since it was deployed",
    )


class ScreeningModel(models.Model):
    """A screening model as it was deployed, at the threshold its laboratory
    director chose; the file itself stays on disk."""

    run_id = models.CharField(max_length=64)
    sha256 = models.CharField(max_length=64)
    stored_at = models.DateTimeField()
    federated_auroc = models.FloatField()
    threshold = models.FloatField()
    # The confusion matrix at the threshold, and AUROC.
    local_validation = models.JSONField(default=dict)

    class Meta:
        constraints = (
            models.UniqueConstraint(
                fields=["run_id", "sha256", "threshold"],
                name="one_record_per_file_and_threshold",
            ),
            models.CheckConstraint(
                condition=models.Q(threshold__gt=0, threshold__lt=1),
                name="threshold_between_zero_and_one",
                violation_error_code="threshold_not_between_zero_and_one",
                violation_error_message="A threshold lies between 0 and 1.",
            ),
        )

    def __str__(self) -> str:
        return self.run_id

    @property
    def name(self) -> str:
        return model_name(self.stored_at)


class DeploymentManager(models.Manager["Deployment"]):
    @transaction.atomic
    def deploy(
        self, *, run_id: str, threshold: float, directory: Path | None, now: datetime
    ) -> Deployment:
        """Make a screening model in the hospital's folder the deployed model, at a
        threshold its local validation holds, from `now`."""
        path = None if directory is None else final_model_path(directory, run_id)
        # One read: what is checked is what is hashed.
        data = path.read_bytes() if path is not None and path.is_file() else None
        file = None if data is None else screening_model_file(data)
        # A missing file and an unreadable one alike: neither is listed.
        if data is None or file is None:
            raise ValidationError(
                f"There is no readable model of run {run_id}.", code="not_found"
            )
        validation = file.at(threshold)
        if validation is None:
            raise ValidationError(
                {
                    "threshold": ValidationError(
                        f"{file.name} has no local validation at threshold"
                        f" {threshold:.2f}.",
                        code="threshold_not_offered",
                    )
                }
            )
        screening_model, _ = ScreeningModel.objects.get_or_create(
            run_id=run_id,
            sha256=sha256(data),
            threshold=threshold,
            defaults={
                "stored_at": file.stored_at,
                "federated_auroc": file.federated_auroc,
                "local_validation": {**validation.counts, "auroc": file.local_auroc},
            },
        )
        return self.create(screening_model=screening_model, deployed_at=now)

    def screener(self, directory: Path | None) -> Screener | NoUsableModel:
        """The deployed model ready to screen, or why there is none."""
        latest = (
            self.select_related("screening_model")
            .order_by("-deployed_at", "-pk")
            .first()
        )
        if latest is None:
            return NoUsableModel.NO_DEPLOYED_MODEL
        screening_model = latest.screening_model
        path = (
            None
            if directory is None
            else final_model_path(directory, screening_model.run_id)
        )
        data = path.read_bytes() if path is not None and path.is_file() else None
        file = None if data is None else screening_model_file(data)
        if data is None or file is None or sha256(data) != screening_model.sha256:
            return NoUsableModel.DEPLOYED_MODEL_CHANGED
        return Screener(screening_model, file)


class Deployment(models.Model):
    """One deployment; the latest names the deployed model. Nothing about who or why."""

    screening_model = models.ForeignKey(
        ScreeningModel, on_delete=models.PROTECT, related_name="deployments"
    )
    deployed_at = models.DateTimeField()

    objects = DeploymentManager()


@dataclass(frozen=True)
class Screener:
    """The deployed model, loaded from the very bytes whose hash was checked (features/hospital/screening.feature)."""

    screening_model: ScreeningModel
    file: ScreeningModelFile

    def suggests_ferritin(self, cbc: Mapping[str, float], age: int) -> bool:
        """Whether the deployed model scores the CBC at or above the threshold the
        laboratory director deployed it at."""
        file = self.file
        score = probability(file.state_dict, file.mean, file.std, cbc, age)
        return score >= self.screening_model.threshold
