"""The screening models the laboratory director deployed (features/hospital/deployment.feature)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction

from ml.inference import probability
from web.hospital.deployment.model_files import (
    ScreeningModel,
    model_name,
    read_stored,
)
from web.shared.accounts.models import User


class NoUsableModel(models.TextChoices):
    """Why no deployed screening model can screen, as the Models page says. A CBC
    analysed meanwhile records only that screening failed, not why."""

    NO_DEPLOYED_MODEL = "no_deployed_model", "No screening model is deployed"
    DEPLOYED_MODEL_CHANGED = (
        "deployed_model_changed",
        "The deployed screening model changed on disk since it was deployed",
    )


class TargetPercent(models.IntegerChoices):
    """The target sensitivities a laboratory director can set. Below 80% the
    screening would miss more than one in five iron-deficient women."""

    EIGHTY = 80, "80%"
    EIGHTY_FIVE = 85, "85%"
    NINETY = 90, "90%"
    NINETY_FIVE = 95, "95%"
    ALL = 100, "100%"


def target_percent_offered(name: str) -> models.CheckConstraint:
    return models.CheckConstraint(
        condition=models.Q(**{f"{name}__in": TargetPercent.values}),
        name=f"{name}_offered",
        violation_error_code="target_sensitivity_not_offered",
        violation_error_message="A target sensitivity is one of 80, 85, 90, 95 and 100%.",
    )


class TargetSensitivityManager(models.Manager["TargetSensitivity"]):
    def current(self) -> TargetSensitivity | None:
        """The target sensitivity set last; None until the director sets one."""
        return self.order_by("-set_at", "-pk").first()

    @transaction.atomic
    def set(
        self, *, percent: int, by: User, directory: Path, now: datetime
    ) -> TargetSensitivity:
        """Make `percent` the target sensitivity from `now`. The deployed
        screening model is redeployed at it, so screening follows the policy at
        once. One whose file changed on disk is not: it no longer screens, and
        its changed file never should."""
        target = self.model(percent=percent, set_at=now, set_by=by)
        target.full_clean()
        target.save()
        screener = Deployment.objects.screener(directory)
        if isinstance(screener, Screener):
            Deployment.objects.record(
                screener.file,
                screener.deployed_screening_model.sha256,
                target_sensitivity=percent,
                by=by,
                now=now,
            )
        return target


class TargetSensitivity(models.Model):
    """The share of iron-deficient past patients the laboratory director wants
    each deployed screening model to suggest ferritin for: the hospital's
    screening policy. The latest is the one in force."""

    percent = models.PositiveSmallIntegerField(choices=TargetPercent.choices)
    set_at = models.DateTimeField()
    set_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )

    objects = TargetSensitivityManager()

    class Meta:
        constraints = (target_percent_offered("percent"),)

    def __str__(self) -> str:
        return f"{self.percent}%"


class DeployedScreeningModel(models.Model):
    """A screening model as it was deployed, at the threshold its target
    sensitivity resolved to. The file itself stays on disk; the SHA-256 here
    detects a change to it."""

    run_id = models.CharField(max_length=64)
    sha256 = models.CharField(max_length=64)
    stored_at = models.DateTimeField()
    federated_auroc = models.FloatField()
    threshold = models.FloatField()
    # The confusion matrix at the threshold, and the AUROC.
    local_validation = models.JSONField(default=dict)

    class Meta:
        constraints = (
            models.UniqueConstraint(
                fields=["run_id", "sha256", "threshold"],
                name="one_record_per_file_and_threshold",
            ),
            models.CheckConstraint(
                condition=models.Q(threshold__gte=0, threshold__lte=1),
                name="threshold_from_zero_to_one",
                violation_error_code="threshold_not_from_zero_to_one",
                violation_error_message="A threshold lies from 0 to 1.",
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
        self, *, run_id: str, by: User, directory: Path, now: datetime
    ) -> Deployment:
        """Make a screening model in the hospital's folder the deployed screening
        model from `now`, at the target sensitivity in force."""
        target = TargetSensitivity.objects.current()
        if target is None:
            raise ValidationError(
                "Set a target sensitivity before deploying a screening model.",
                code="no_target_sensitivity",
            )
        stored = read_stored(directory, run_id)
        # A missing file and an unreadable one get the same error, because the
        # Models page lists neither.
        if stored is None:
            raise ValidationError(
                f"There is no readable model of run {run_id}.", code="not_found"
            )
        file, digest = stored
        return self.record(
            file, digest, target_sensitivity=target.percent, by=by, now=now
        )

    @transaction.atomic
    def record(
        self,
        file: ScreeningModel,
        digest: str,
        *,
        target_sensitivity: int,
        by: User,
        now: datetime,
    ) -> Deployment:
        """Deploy `file`, read from bytes whose SHA-256 is `digest`, at the
        highest threshold that reaches `target_sensitivity`."""
        validation = file.at_target(target_sensitivity)
        deployed_screening_model, _ = DeployedScreeningModel.objects.get_or_create(
            run_id=file.run_id,
            sha256=digest,
            threshold=validation.threshold,
            defaults={
                "stored_at": file.stored_at,
                "federated_auroc": file.federated_auroc,
                "local_validation": {**validation.counts, "auroc": file.local_auroc},
            },
        )
        return self.create(
            deployed_screening_model=deployed_screening_model,
            deployed_at=now,
            deployed_by=by,
            target_sensitivity=target_sensitivity,
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
        stored = read_stored(directory, deployed_screening_model.run_id)
        if stored is None or stored[1] != deployed_screening_model.sha256:
            return NoUsableModel.DEPLOYED_MODEL_CHANGED
        return Screener(deployed_screening_model, stored[0])


class Deployment(models.Model):
    """One deployment; the latest names the deployed screening model. It records
    who deployed it, and the target sensitivity its threshold came from."""

    deployed_screening_model = models.ForeignKey(
        DeployedScreeningModel, on_delete=models.PROTECT, related_name="deployments"
    )
    deployed_at = models.DateTimeField()
    deployed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    target_sensitivity = models.PositiveSmallIntegerField(choices=TargetPercent.choices)

    objects = DeploymentManager()

    class Meta:
        constraints = (target_percent_offered("target_sensitivity"),)


@dataclass(frozen=True)
class Screener:
    """The deployed screening model, loaded from the same bytes whose hash was
    checked."""

    deployed_screening_model: DeployedScreeningModel
    file: ScreeningModel

    def suggests_ferritin(self, cbc: Mapping[str, float], age: int) -> bool:
        """Whether the model scores the CBC at or above the threshold the
        laboratory director deployed it at."""
        file = self.file
        score = probability(file.state_dict, file.mean, file.std, cbc, age)
        return score >= self.deployed_screening_model.threshold
