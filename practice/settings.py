"""A general practitioner's practice's web app: patients, samples, orders and
lab reports."""

import os

from shared.accounts.roles import Role
from shared.settings import *

DATA_DIR = data_dir("practice")
DATABASES = databases(DATA_DIR)
SECRET_KEY = secret_key(DATA_DIR)
SESSION_COOKIE_NAME, CSRF_COOKIE_NAME = cookie_names(DATA_DIR)

# This party's own apps; no other party installs them.
INSTALLED_APPS = [
    *SHARED_APPS,
    "practice",
]
ROLES = [Role.GENERAL_PRACTITIONER]
ROOT_URLCONF = "practice.urls"
PARTY_NAME = os.environ.get("PARTY_NAME") or "Demo practice"
PRACTICE_CERTIFICATE_NAME = os.environ.get("PRACTICE_CERTIFICATE_NAME", "demo-practice")
