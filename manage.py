#!/usr/bin/env python
"""Django's command-line utility for one party's web app. DJANGO_SETTINGS_MODULE
names the party's settings: web.hospital.settings, web.practice.settings or
web.startup.settings."""

import os
import sys

if __name__ == "__main__":
    if "DJANGO_SETTINGS_MODULE" not in os.environ:
        sys.exit(
            "Set DJANGO_SETTINGS_MODULE to the party's settings: web.hospital.settings,"
            " web.practice.settings or web.startup.settings."
        )
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)
