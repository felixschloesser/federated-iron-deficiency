"""Print one line on this hospital's screening models: how many, which is deployed."""

from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand

from web.deployment.domain import deployed_model, screening_models


class Command(BaseCommand):
    help = __doc__

    def handle(self, *args: Any, **options: Any) -> None:
        directory = settings.FINAL_MODELS_DIR
        count = len(screening_models(directory))
        deployed, no_usable_model = deployed_model(directory)
        if count == 0:
            line = "no screening model yet"
        elif deployed is None:
            line = f"{count} screening model{'s' if count > 1 else ''}, none deployed"
        elif no_usable_model is not None:
            line = f"{no_usable_model.label} ({count} in all)"
        else:
            line = f"{deployed.name} deployed ({count} in all)"
        self.stdout.write(line)
