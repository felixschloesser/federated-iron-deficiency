"""Register a practice the hospital works with by its name, which never changes
(features/hospital/lab_orders.feature); run again, it changes nothing."""

from typing import Any

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError, CommandParser

from web.hospital.lab.models import Practice


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("name", help='for example "Huisartsenpraktijk De Ceder"')

    def handle(self, *args: Any, **options: Any) -> None:
        try:
            practice = Practice.objects.add(name=options["name"])
        except ValidationError as error:
            raise CommandError("; ".join(error.messages)) from error
        self.stdout.write(f"{practice.name} calls as {practice.slug}")
