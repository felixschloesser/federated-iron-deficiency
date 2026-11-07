"""Register a practice the hospital works with, by the certificate name the
hospital issued it, or change its name (features/hospital/lab_orders.feature)."""

from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from web.hospital.lab.models import Practice


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "certificate_name", help="what its app sends in every message: de-ceder"
        )
        parser.add_argument(
            "name", help='as the hospital knows it: "Huisartsenpraktijk De Ceder"'
        )

    def handle(self, *args: Any, **options: Any) -> None:
        practice = Practice.objects.add(
            certificate_name=options["certificate_name"], name=options["name"]
        )
        self.stdout.write(f"{practice.name} as {practice.certificate_name}")
