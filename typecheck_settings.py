"""For mypy only (django-stubs reads one settings module), at the top so no party and no shared code imports it: every party's apps
together, so it can type every model. No web app runs with it."""

from hospital import settings as hospital
from practice import settings as practice
from shared.settings import *
from startup import settings as startup

INSTALLED_APPS = list(
    dict.fromkeys(
        [*hospital.INSTALLED_APPS, *practice.INSTALLED_APPS, *startup.INSTALLED_APPS]
    )
)
DATABASES = hospital.DATABASES
SECRET_KEY = hospital.SECRET_KEY
