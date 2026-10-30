"""Run the hospital's messaging endpoint (spec §10, R22-R25) until stopped."""

from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser

from web.lab.messaging import serve


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("address", help="host:port, for example 127.0.0.1:8443")

    def handle(self, *args: Any, **options: Any) -> None:
        folder = settings.HOSPITAL_DIR
        if folder is None:
            raise CommandError("Set HOSPITAL_DIR: the certificates live there.")
        server, _ = serve(
            options["address"],
            certificate=(folder / "messaging" / "certificate.pem").read_bytes(),
            private_key=(folder / "messaging" / "key.pem").read_bytes(),
            # Only the practice this hospital's own CA certified gets in (R24).
            client_authority=(folder / "ca" / "ca.crt").read_bytes(),
        )
        self.stdout.write(f"Messaging endpoint on {options['address']}")
        # The demo sends stdout to a file, which would hold the line until exit.
        self.stdout.flush()
        server.wait_for_termination()
