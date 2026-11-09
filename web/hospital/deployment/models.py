"""The screening models the laboratory director deployed (features/hospital/deployment.feature)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from django.core.exceptions import ValidationError
from django.db import models, transaction

from ml.final_model import model_file_path
from ml.inference import probability
from web.hospital.deployment.model_files import (
    ScreeningModel,
    model_name,
    read_screening_model,
    sha256,
)


class NoUsableModel(models.TextChoices):
    """Why no deployed screening model can screen, as the Models page says; a CBC
    analysed meanwhile records only that screening failed."""

    NO_DEPLOYED_MODEL = "no_deployed_model", "No screening model is deployed"
    DEPLOYED_MODEL_CHANGED = (
        "deployed_model_changed",
        "The deployed screening model changed on disk since it was deployed",
    )


class DeployedScreeningModel(models.Model):
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
        self, *, run_id: str, threshold: float, directory: Path, now: datetime
    ) -> Deployment:
        """Make a screening model in the hospital's folder the deployed screening model, at a
        threshold its local validation holds, from `now`."""
        path = model_file_path(directory, run_id)
        # One read: what is checked is what is hashed.
        data = path.read_bytes() if path.is_file() else None
        file = None if data is None else read_screening_model(data)
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
        deployed_screening_model, _ = DeployedScreeningModel.objects.get_or_create(
            run_id=run_id,
            sha256=sha256(data),
            threshold=threshold,
            defaults={
                "stored_at": file.stored_at,
                "federated_auroc": file.federated_auroc,
                "local_validation": {**validation.counts, "auroc": file.local_auroc},
            },
        )
        return self.create(
            deployed_screening_model=deployed_screening_model, deployed_at=now
        )

    def screener(self, directory: Path) -> Screener | NoUsableModel:
        """The deployed screening model ready to screen, or why there is none."""
        latest = (
            self.select_related("deployed_screening_model")
            .order_by("-deployed_at", "-pk")
            .first()
        )
        if latest is None:
            return NoUsableModel.NO_DEPLOYED_MODEL
        deployed_screening_model = latest.deployed_screening_model
        path = model_file_path(directory, deployed_screening_model.run_id)
        data = path.read_bytes() if path.is_file() else None
        file = None if data is None else read_screening_model(data)
        if (
            data is None
            or file is None
            or sha256(data) != deployed_screening_model.sha256
        ):
            return NoUsableModel.DEPLOYED_MODEL_CHANGED
        return Screener(deployed_screening_model, file)


class Deployment(models.Model):
    """One deployment; the latest names the deployed screening model. Nothing about who or why."""

    deployed_screening_model = models.ForeignKey(
        DeployedScreeningModel, on_delete=models.PROTECT, related_name="deployments"
    )
    deployed_at = models.DateTimeField()

    objects = DeploymentManager()


@dataclass(frozen=True)
class Screener:
    """The deployed screening model, loaded from the very bytes whose hash was checked (features/hospital/screening.feature)."""

    deployed_screening_model: DeployedScreeningModel
    file: ScreeningModel

    def suggests_ferritin(self, cbc: Mapping[str, float], age: int) -> bool:
        """Whether the deployed screening model scores the CBC at or above the threshold the
        laboratory director deployed it at."""
        file = self.file
        score = probability(file.state_dict, file.mean, file.std, cbc, age)
        return score >= self.deployed_screening_model.threshold
