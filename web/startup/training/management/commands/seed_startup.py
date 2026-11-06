"""Create the startup's demo data scientist; the startup holds no patients."""

from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from web.accounts.roles import Role
from web.seeding.accounts import DATA_SCIENTIST, PASSWORD
from web.seeding.command import user


class Command(BaseCommand):
    help = __doc__

    def handle(self, *args: Any, **options: Any) -> None:
        if not settings.DEBUG:
            raise CommandError(
                "Demo accounts share a known password; run with DJANGO_DEBUG=1."
            )
        with transaction.atomic():
            user(DATA_SCIENTIST, Role.DATA_SCIENTIST)
            user("no-role", None)  # Has no role: for the refusal at login.
        self.stdout.write(f"Accounts {DATA_SCIENTIST} and no-role, password {PASSWORD}")
