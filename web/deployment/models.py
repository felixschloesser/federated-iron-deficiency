"""Laboratory directors, and the screening models they deployed (features/deployment.feature)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction

from iron_deficiency.screening import (
    FinalModel,
    final_model_path,
    from_bytes,
    suggests_ferritin,
)
from web.deployment.model_files import (
    CannotDeploy,
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


class LaboratoryDirector(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="laboratory_director",
    )
    name = models.CharField(max_length=100)

    class Meta:
        constraints = (
            # A hospital has one laboratory director (features/deployment.feature): any second row
            # repeats the constant.
            models.UniqueConstraint(
                models.Value(1),
                name="one_laboratory_director",
                violation_error_code="one_laboratory_director",
                violation_error_message="A hospital has one laboratory director.",
            ),
        )

    def __str__(self) -> str:
        return self.name


class ScreeningModel(models.Model):
    """A screening model as it was when deployed; the file itself stays on disk."""

    run_id = models.CharField(max_length=64)
    sha256 = models.CharField(max_length=64)
    # Absent in a file that does not record them.
    stored_at = models.DateTimeField(null=True, blank=True)
    federated_auroc = models.FloatField(null=True, blank=True)
    threshold = models.FloatField()
    local_validation = models.JSONField(default=dict)

    class Meta:
        constraints = (
            models.UniqueConstraint(
                fields=["run_id", "sha256"], name="one_record_per_file"
            ),
        )

    def __str__(self) -> str:
        return self.run_id

    @property
    def name(self) -> str:
        return model_name(self.stored_at, self.run_id)


class DeploymentManager(models.Manager["Deployment"]):
    @transaction.atomic
    def deploy(
        self, *, run_id: str, directory: Path | None, now: datetime
    ) -> Deployment:
        """Make a screening model in the hospital's folder the deployed model, from
        `now` (features/deployment.feature)."""
        path = None if directory is None else final_model_path(directory, run_id)
        if path is None or not path.is_file():
            raise ValidationError(
                f"There is no model of run {run_id}.", code="not_found"
            )
        # One read: what is checked is what is hashed.
        data = path.read_bytes()
        file = screening_model_file(run_id, data)
        threshold = file.threshold
        if file.problem is not None or threshold is None:
            # Without a problem a file has a threshold; the second test only narrows
            # the type.
            problem = file.problem or CannotDeploy.THRESHOLD_MISSING
            raise ValidationError(
                f"{file.name} cannot be deployed: {problem.label}.",
                code=problem.value,
            )
        screening_model, _ = ScreeningModel.objects.get_or_create(
            run_id=run_id,
            sha256=sha256(data),
            defaults={
                "stored_at": file.stored_at,
                "threshold": threshold,
                "federated_auroc": file.federated_auroc,
                "local_validation": file.local_validation,
            },
        )
        return self.create(screening_model=screening_model, deployed_at=now)

    def screener(self, directory: Path | None) -> Screener | NoUsableModel:
        """The deployed model ready to screen, or why there is none (features/screening.feature)."""
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
        if data is None or sha256(data) != screening_model.sha256:
            return NoUsableModel.DEPLOYED_MODEL_CHANGED
        return Screener(screening_model, from_bytes(data))


class Deployment(models.Model):
    """One deployment; the latest names the deployed model. Nothing about who or why."""

    screening_model = models.ForeignKey(
        ScreeningModel, on_delete=models.PROTECT, related_name="deployments"
    )
    deployed_at = models.DateTimeField()

    objects = DeploymentManager()


@dataclass(frozen=True)
class Screener:
    """The deployed model, loaded from the very bytes whose hash was checked (features/screening.feature)."""

    screening_model: ScreeningModel
    final_model: FinalModel

    def suggests_ferritin(self, cbc: Mapping[str, float], age: int) -> bool:
        return suggests_ferritin(cbc, age, self.final_model)
