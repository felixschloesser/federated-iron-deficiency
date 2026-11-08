"""Run the startup's messaging endpoint (features/startup/release.feature) until stopped."""

from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from web.startup.training.messaging import serve


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("address", help="host:port, for example 127.0.0.1:8442")

    def handle(self, *args: Any, **options: Any) -> None:
        server, _ = serve(options["address"])
        self.stdout.write(f"Messaging endpoint on {options['address']}")
        # The demo sends stdout to a file, which would hold the line until exit.
        self.stdout.flush()
        server.wait_for_termination()
