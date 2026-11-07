"""Add a laboratory the practice sends samples to, or change its address; with
--primary, the one samples go to unless the general practitioner picks another (features/practice/ordering.feature)."""

from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from practice.models import Laboratory


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "name", help='as the general practitioner reads it: "UZ Leuven"'
        )
        parser.add_argument(
            "address", help="its hospital's messaging endpoint, host:port"
        )
        parser.add_argument(
            "--primary",
            action="store_true",
            help="samples go there unless the general practitioner picks another",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        laboratory = Laboratory.objects.add(
            name=options["name"],
            address=options["address"],
            primary=options["primary"],
        )
        self.stdout.write(f"{laboratory.name} at {laboratory.address}")
