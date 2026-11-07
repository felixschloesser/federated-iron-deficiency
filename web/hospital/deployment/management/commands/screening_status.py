"""Print one line on this hospital's screening models: how many, which is deployed."""

from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand

from web.hospital.deployment.model_files import screening_models
from web.hospital.deployment.models import Deployment, NoUsableModel


class Command(BaseCommand):
    help = __doc__

    def handle(self, *args: Any, **options: Any) -> None:
        directory = settings.SCREENING_MODELS_DIR
        count = len(screening_models(directory))
        deployed = Deployment.objects.screener(directory)
        if count == 0:
            line = "no screening model yet"
        elif deployed is NoUsableModel.NO_DEPLOYED_MODEL:
            line = f"{count} screening model{'s' if count > 1 else ''}, none deployed"
        elif isinstance(deployed, NoUsableModel):
            line = f"{deployed.label} ({count} in all)"
        else:
            line = f"{deployed.screening_model.name} deployed ({count} in all)"
        self.stdout.write(line)
