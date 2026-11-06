#!/usr/bin/env python
"""Django's command-line utility, as one party's web app: DJANGO_SETTINGS_MODULE
names its settings, web.settings.hospital, web.settings.practice or
web.settings.startup."""

import os
import sys

if __name__ == "__main__":
    if "DJANGO_SETTINGS_MODULE" not in os.environ:
        sys.exit(
            "Set DJANGO_SETTINGS_MODULE to the party's settings: web.settings.hospital,"
            " web.settings.practice or web.settings.startup."
        )
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)
