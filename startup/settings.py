"""The startup's web app: its data scientist's training runs and final models."""

import os

from shared.accounts.roles import Role
from shared.settings import *

DATA_DIR = data_dir("startup")
DATABASES = databases(DATA_DIR)
SECRET_KEY = secret_key(DATA_DIR)
SESSION_COOKIE_NAME, CSRF_COOKIE_NAME = cookie_names(DATA_DIR)

# This party's own apps; no other party installs them.
INSTALLED_APPS = [
    *SHARED_APPS,
    "startup.training",
]
ROLES = [Role.DATA_SCIENTIST]
ROOT_URLCONF = "startup.urls"
PARTY_NAME = os.environ.get("PARTY_NAME") or "Demo startup"
FINAL_MODELS_DIR = DATA_DIR / "final-models"
