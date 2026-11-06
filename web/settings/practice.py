"""A general practitioner's practice's web app: patients, samples, orders and
lab reports."""

import os

from web.accounts.roles import Role
from web.settings.base import *

DATA_DIR = data_dir("practice")
DATABASES = databases(DATA_DIR)
SECRET_KEY = secret_key(DATA_DIR)
SESSION_COOKIE_NAME, CSRF_COOKIE_NAME = cookie_names(DATA_DIR)

# This party's own apps; no other party installs them.
INSTALLED_APPS = [
    *SHARED_APPS,
    "web.practice",
]
ROLES = [Role.GENERAL_PRACTITIONER]
ROOT_URLCONF = "web.urls.practice"
PARTY_NAME = os.environ.get("PARTY_NAME") or "Demo practice"
PRACTICE_CERTIFICATE_NAME = os.environ.get("PRACTICE_CERTIFICATE_NAME", "demo-practice")
