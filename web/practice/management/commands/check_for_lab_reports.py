"""Send pending lab orders and fetch new lab reports from the hospital (R23)."""

import time
from typing import Any

import grpc
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.utils import timezone

from web.messaging import client


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--every", type=int, help="seconds between checks; once without it"
        )

    def handle(self, *args: Any, **options: Any) -> None:
        connection = client.configured_connection()
        if connection is None:
            raise CommandError("Set PRACTICE_DIR and MESSAGING_ADDRESS first.")
        every = options["every"]
        while True:
            try:
                fetched = client.check_for_lab_reports(connection, now=timezone.now())
            except grpc.RpcError as error:
                if every is None:
                    raise CommandError(f"The hospital: {error.code()}") from error
                # The hospital may start later or be down for a while: try again.
                self.stderr.write(f"The hospital could not be reached: {error.code()}")
            else:
                self.stdout.write(f"{fetched} new lab reports")
            if every is None:
                return
            time.sleep(every)
