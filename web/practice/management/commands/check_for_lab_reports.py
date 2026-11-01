"""Send pending lab orders and fetch new lab reports from the hospital (R23)."""

import time
from typing import Any

import grpc
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.utils import timezone

from web.practice import messaging


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--repeat",
            action="store_true",
            help="check every REPORT_CHECK_SECONDS; once without it",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        connection = messaging.configured_connection()
        if connection is None:
            raise CommandError("Set PRACTICE_DIR and MESSAGING_ADDRESS first.")
        repeat = options["repeat"]
        while True:
            try:
                fetched = messaging.check_for_lab_reports(
                    connection, now=timezone.now()
                )
            except grpc.RpcError as error:
                if not repeat:
                    raise CommandError(f"The hospital: {error.code()}") from error
                # The hospital may start later or be down for a while: try again.
                self.stderr.write(f"The hospital could not be reached: {error.code()}")
            else:
                self.stdout.write(f"{fetched} new lab reports")
            if not repeat:
                return
            time.sleep(settings.REPORT_CHECK_SECONDS)
