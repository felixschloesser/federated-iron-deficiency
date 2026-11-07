"""For mypy only (django-stubs reads one settings module): every party's apps
together, so it can type every model. No web app runs with it."""

from web.settings import hospital, practice, startup
from web.settings.base import *

INSTALLED_APPS = list(
    dict.fromkeys(
        [*hospital.INSTALLED_APPS, *practice.INSTALLED_APPS, *startup.INSTALLED_APPS]
    )
)
DATABASES = hospital.DATABASES
SECRET_KEY = hospital.SECRET_KEY
