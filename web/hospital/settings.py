"""The hospital's web app: the laboratory, its analyser stand-in, and the
screening models the laboratory director deploys."""

import os
from typing import Any

from web.shared.accounts.roles import Role
from web.shared.settings import *

DATA_DIR = data_dir("hospital")
DATABASES: dict[str, Any] = databases(DATA_DIR)
SECRET_KEY: str = secret_key(DATA_DIR)
SESSION_COOKIE_NAME, CSRF_COOKIE_NAME = cookie_names(DATA_DIR)

# This party's own apps; no other party installs them.
INSTALLED_APPS: list[str] = [
    *SHARED_APPS,
    "web.hospital.analyser",
    "web.hospital.lab",
    "web.hospital.deployment",
    "web.hospital.cohort",
]
ROLES = [Role.LABORATORY_STAFF, Role.LABORATORY_DIRECTOR]
ROOT_URLCONF = "web.hospital.urls"
PARTY_NAME = os.environ.get("PARTY_NAME") or "Demo hospital"
SCREENING_MODELS_DIR = DATA_DIR / "screening-models"
TRAINING_COHORT_DIR = DATA_DIR / "cohort"
# The startup's final-models endpoint (host:port) and the name the startup issued
# this hospital and knows it by (glossary.toml, certificate name); without the
# endpoint, the hospital offers no fetching.
STARTUP_ADDRESS = os.environ.get("STARTUP_ADDRESS") or None
HOSPITAL_CERTIFICATE_NAME = os.environ.get("HOSPITAL_CERTIFICATE_NAME")
