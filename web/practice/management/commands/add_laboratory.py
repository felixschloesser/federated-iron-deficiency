"""Add a laboratory the practice sends samples to, or change its address (R22)."""

from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from web.practice.models import Laboratory


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "name", help='as the general practitioner reads it: "UZ Leuven"'
        )
        parser.add_argument(
            "address", help="its hospital's messaging endpoint, host:port"
        )

    def handle(self, *args: Any, **options: Any) -> None:
        laboratory, _ = Laboratory.objects.update_or_create(
            name=options["name"], defaults={"address": options["address"]}
        )
        self.stdout.write(f"{laboratory.name} at {laboratory.address}")
