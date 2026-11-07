"""Register a recipient hospital by its name, which never changes
(features/startup/release.feature); run again, it changes nothing."""

from typing import Any

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError, CommandParser

from web.startup.training.models import Recipient


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("name", help='for example "UZ Leuven"')

    def handle(self, *args: Any, **options: Any) -> None:
        try:
            recipient = Recipient.objects.add(name=options["name"])
        except ValidationError as error:
            raise CommandError("; ".join(error.messages)) from error
        self.stdout.write(f"{recipient} may fetch released final models.")
