"""Run the startup's screening-models gRPC endpoint until stopped.

See features/startup/release.feature."""

from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from web.startup.training.grpc_server import serve


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("address", help="host:port, for example 127.0.0.1:8442")

    def handle(self, *args: Any, **options: Any) -> None:
        server, _ = serve(options["address"])
        self.stdout.write(f"Screening-models endpoint on {options['address']}")
        # The demo redirects stdout to a file, which would buffer this line until
        # exit.
        self.stdout.flush()
        server.wait_for_termination()
