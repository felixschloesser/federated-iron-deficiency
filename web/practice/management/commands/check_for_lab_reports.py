"""Send pending lab orders and fetch new lab reports from every laboratory (R23)."""

import time
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.utils import timezone

from web.practice import messaging
from web.practice.models import Laboratory


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--repeat",
            action="store_true",
            help="check every REPORT_CHECK_SECONDS; once without it",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        if settings.PARTY_DIR is None or not Laboratory.objects.exists():
            raise CommandError(
                "No laboratory to ask: set PRACTICE_DIR and run add_laboratory."
            )
        repeat = options["repeat"]
        while True:
            check = messaging.check_every_laboratory(now=timezone.now())
            for laboratory, error in check.failures:
                # A hospital may start later or be down for a while: try again.
                self.stderr.write(f"{laboratory} could not be reached: {error.code()}")
            self.stdout.write(f"{check.fetched} new lab reports")
            if not repeat:
                if check.failures:
                    raise CommandError(
                        f"{len(check.failures)} of {check.asked} laboratories failed."
                    )
                return
            time.sleep(settings.REPORT_CHECK_SECONDS)
