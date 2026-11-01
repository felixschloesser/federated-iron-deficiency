"""Deploying a screening model (R18)."""

from datetime import datetime
from pathlib import Path

from django.core.exceptions import ValidationError
from django.db import transaction

from web.deployment.domain import CannotDeploy, read_screening_model_file, sha256
from web.deployment.models import Deployment, ScreeningModel


@transaction.atomic
def deploy(*, run_id: str, directory: Path | None, now: datetime) -> Deployment:
    """Make a screening model in the hospital's folder the deployed model, from `now`."""
    path = None if directory is None else directory / f"{run_id}.pt"
    if path is None or not path.is_file():
        raise ValidationError(f"There is no model of run {run_id}.", code="not_found")
    file = read_screening_model_file(path)
    threshold = file.threshold
    if file.problem is not None or threshold is None:
        # Without a problem a file has a threshold; the second test only narrows the type.
        problem = file.problem or CannotDeploy.THRESHOLD_MISSING
        raise ValidationError(
            f"{file.name} cannot be deployed: {problem.label}.",
            code=problem.value,
        )
    screening_model, _ = ScreeningModel.objects.get_or_create(
        run_id=run_id,
        sha256=sha256(path),
        defaults={
            "stored_at": file.stored_at,
            "threshold": threshold,
            "federated_auroc": file.federated_auroc,
            "local_validation": file.local_validation,
        },
    )
    return Deployment.objects.create(screening_model=screening_model, deployed_at=now)
