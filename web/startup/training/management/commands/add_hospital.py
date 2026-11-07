"""Register a recipient hospital by the certificate name the startup issued it
(features/startup/release.feature); run again to change its name."""

from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from web.startup.training.models import Recipient


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("certificate_name", help="for example uz-leuven")
        parser.add_argument("name", help="for example UZ Leuven")

    def handle(self, *args: Any, **options: Any) -> None:
        recipient = Recipient.objects.add(
            certificate_name=options["certificate_name"], name=options["name"]
        )
        self.stdout.write(f"{recipient} may fetch released final models.")
