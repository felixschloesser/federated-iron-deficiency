"""The startup's web app: its data scientist's training runs and final models."""

from pathlib import Path
from typing import Any

from web.shared.accounts.roles import Role
from web.shared.settings import *

DATA_DIR: Path = data_dir("startup")
DATABASES: dict[str, Any] = databases(DATA_DIR)
SECRET_KEY: str = secret_key(DATA_DIR)
SESSION_COOKIE_NAME, CSRF_COOKIE_NAME = cookie_names(DATA_DIR)

# This party's own apps; no other party installs them.
INSTALLED_APPS: list[str] = [
    *SHARED_APPS,
    "web.startup.training",
]
ROLES = [Role.DATA_SCIENTIST]
ROOT_URLCONF = "web.startup.urls"
# The ServerApp writes here and only checks the folder exists, so the web app,
# which owns it, creates it (in the demo, the startup's image already has).
FINAL_MODELS_DIR: Path = DATA_DIR / "final-models"
FINAL_MODELS_DIR.mkdir(exist_ok=True)
