"""For mypy only (django-stubs reads one settings module), at the top so no party and no shared code imports it: every party's apps
together, so it can type every model. No web app runs with it."""

from web.hospital import settings as hospital
from web.practice import settings as practice
from web.shared.settings import *
from web.startup import settings as startup

INSTALLED_APPS = list(
    dict.fromkeys(
        [*hospital.INSTALLED_APPS, *practice.INSTALLED_APPS, *startup.INSTALLED_APPS]
    )
)
DATABASES = hospital.DATABASES
SECRET_KEY = hospital.SECRET_KEY
DATA_DIR = hospital.DATA_DIR
SCREENING_MODELS_DIR = hospital.SCREENING_MODELS_DIR
TRAINING_COHORT_DIR = hospital.TRAINING_COHORT_DIR
STARTUP_ADDRESS = hospital.STARTUP_ADDRESS
FINAL_MODELS_DIR = startup.FINAL_MODELS_DIR
