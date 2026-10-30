"""Laboratory directors, and the final models they deployed (spec R18)."""

from django.conf import settings
from django.db import models


class LaboratoryDirector(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="laboratory_director",
    )
    name = models.CharField(max_length=100)

    def __str__(self) -> str:
        return self.name


class FinalModel(models.Model):
    """A final model as it was when deployed; the file itself stays on disk."""

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


class Deployment(models.Model):
    """One deployment; the latest names the deployed model. Nothing about who or why."""

    final_model = models.ForeignKey(
        FinalModel, on_delete=models.PROTECT, related_name="deployments"
    )
    deployed_at = models.DateTimeField()
