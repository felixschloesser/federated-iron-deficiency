"""Add a laboratory the practice sends samples to, or change its address (R22, R24).

Its hospital's authority issues the practice a certificate; put it, its key and
the authority's certificate in PRACTICE_DIR/laboratories/<slug>/ first, as
ca.crt, certificate.pem and key.pem, where <slug> is the name in lower case
with dashes ("UZ Leuven": uz-leuven).
"""

from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser

from web.practice.messaging import certificates_of
from web.practice.models import Laboratory

CERTIFICATES = ("ca.crt", "certificate.pem", "key.pem")


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
        if settings.PARTY_DIR is None:
            raise CommandError("Set PRACTICE_DIR: the certificates live there.")
        laboratory = Laboratory(name=options["name"], address=options["address"])
        folder = certificates_of(laboratory, settings.PARTY_DIR)
        # Missing certificates stop it here, not at the first lab order.
        missing = [name for name in CERTIFICATES if not (folder / name).is_file()]
        if missing:
            raise CommandError(f"{folder} lacks {', '.join(missing)}.")
        Laboratory.objects.update_or_create(
            name=laboratory.name, defaults={"address": laboratory.address}
        )
        self.stdout.write(f"{laboratory.name} at {laboratory.address}")
