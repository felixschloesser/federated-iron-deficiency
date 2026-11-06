"""The hospital's web app: the laboratory, its analyser stand-in, and the
screening models the laboratory director deploys."""

import os

from web.accounts.roles import Role
from web.settings.base import *

DATA_DIR = data_dir("hospital")
DATABASES = databases(DATA_DIR)
SECRET_KEY = secret_key(DATA_DIR)
SESSION_COOKIE_NAME, CSRF_COOKIE_NAME = cookie_names(DATA_DIR)

# This party's own apps; no other party installs them.
INSTALLED_APPS = [
    *SHARED_APPS,
    "web.hospital.nhanes",
    "web.hospital.lab",
    "web.hospital.deployment",
]
ROLES = [Role.LABORATORY_STAFF, Role.LABORATORY_DIRECTOR]
ROOT_URLCONF = "web.urls.hospital"
PARTY_NAME = os.environ.get("PARTY_NAME") or "Demo hospital"
SCREENING_MODELS_DIR = DATA_DIR / "screening-models"
