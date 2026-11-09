"""A general practitioner's practice's web app: patients, samples, orders and
lab reports."""

from typing import Any

from web.shared.accounts.roles import Role
from web.shared.settings import *

DATA_DIR = data_dir("practice")
DATABASES: dict[str, Any] = databases(DATA_DIR)
SECRET_KEY: str = secret_key(DATA_DIR)
SESSION_COOKIE_NAME, CSRF_COOKIE_NAME = cookie_names(DATA_DIR)

# This party's own apps; no other party installs them.
INSTALLED_APPS: list[str] = [
    *SHARED_APPS,
    "web.practice",
]
ROLES = [Role.GENERAL_PRACTITIONER]
ROOT_URLCONF = "web.practice.urls"
