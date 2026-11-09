"""WSGI entry point for one party's web app; DJANGO_SETTINGS_MODULE names the
party's settings (web/<party>/settings.py)."""

from django.core.wsgi import get_wsgi_application

application = get_wsgi_application()
