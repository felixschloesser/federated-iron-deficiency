"""What every party's web app shares; each party's module (web/<party>/settings.py,
chosen by DJANGO_SETTINGS_MODULE) adds its apps, roles, pages and
data folder. DEBUG only with DJANGO_DEBUG=1. Plain HTTP: the demo leaves out the
report's TLS."""

import os
from pathlib import Path
from typing import Any

import django_stubs_ext
from django.core.exceptions import ImproperlyConfigured
from django.core.management.utils import get_random_secret_key

from web.shared.accounts.roles import Role

# Lets generic views be subscripted (ListView[Order]) at runtime, as mypy wants.
django_stubs_ext.monkeypatch()

BASE_DIR = Path(__file__).resolve().parent.parent.parent

DEBUG = os.environ.get("DJANGO_DEBUG") == "1"

# Each party's module sets these; here, what a party without them has.
# The roles that log in to this web app (.claude/audit.py checks each role is in
# exactly one party's module).
ROLES: list[Role] = []
# The party's own folder (data_dir()).
DATA_DIR: Path | None = None
# The hospital's screening models.
SCREENING_MODELS_DIR: Path | None = None
# The startup's copy of every final model.
FINAL_MODELS_DIR: Path | None = None
# The training cohort the laboratory director provides, which the startup's
# code at the hospital reads.
TRAINING_COHORT_DIR: Path | None = None
# The name the hospitals issued this practice and know it by, which its app
# names itself by in each call (glossary.toml, certificate name); None, it
# cannot call.
PRACTICE_CERTIFICATE_NAME: str | None = None
# The startup's final-models endpoint and the name the startup issued this
# hospital; without the endpoint, no fetching.
STARTUP_ADDRESS: str | None = None
HOSPITAL_CERTIFICATE_NAME: str | None = None
# Shown in the title bar and header; never the screening's name.
PARTY_NAME = ""


def data_dir(party: str) -> Path:
    """The party's own folder, DATA_DIR (demo/README.md,
    tests/quality/security/test_party_isolation.py): what it stores lives
    there. Without DATA_DIR, the checkout's .data/<party>/, so each worktree
    keeps its own."""
    folder = Path(os.environ.get("DATA_DIR") or BASE_DIR / ".data" / party)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def databases(folder: Path) -> dict[str, Any]:
    """The party's one SQLite file, in its folder."""
    return {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": folder / "web.sqlite3",
            # Two processes write this file (the web app, and messaging): take the
            # write lock at BEGIN, so the second waits instead of failing on its
            # first write.
            "OPTIONS": {"transaction_mode": "IMMEDIATE"},
            # A file, not memory: Django never closes an in-memory database, so
            # the messaging endpoint's threads would leave their connections open
            # in tests.
            "TEST": {"NAME": folder / "test-web.sqlite3"},
        }
    }


def secret_key(folder: Path) -> str:
    """The key from the environment, else one kept in the party's folder."""
    if key := os.environ.get("DJANGO_SECRET_KEY"):
        return key
    path = folder / ".secret_key"
    if not path.exists():
        path.write_text(get_random_secret_key())
        path.chmod(0o600)
    return path.read_text().strip()


def cookie_names(folder: Path) -> tuple[str, str]:
    """The session and CSRF cookies' names, after the party's folder. Browsers
    share cookies between ports of one host, and the demo serves every party
    from 127.0.0.1: without its own names, one party's login would replace
    another's session and CSRF token (a 403 on its next form)."""
    return f"sessionid-{folder.name}", f"csrftoken-{folder.name}"


# A Pico colour theme per party, so its pages are told apart at a glance; absent:
# Pico's default. Only a vendored theme will do.
PICO_DIR = BASE_DIR / "web" / "shared" / "static" / "css" / "vendor" / "pico-2.1.1"
PARTY_COLOUR = os.environ.get("PARTY_COLOUR") or None
if (
    PARTY_COLOUR is not None
    and not (PICO_DIR / f"pico.{PARTY_COLOUR}.min.css").is_file()
):
    raise ImproperlyConfigured(
        f"PARTY_COLOUR {PARTY_COLOUR!r} has no Pico theme in {PICO_DIR}."
    )


# ".localhost": localhost and each <party>.localhost the demo's proxy routes (RFC 6761).
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", ".localhost,127.0.0.1").split(
    ","
)

# What every party installs; each party's module adds its own apps.
SHARED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "web.shared.accounts",
]

AUTH_USER_MODEL = "accounts.User"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Serves the collected stylesheets when DEBUG is off: Django itself does not.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "web.shared.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "web" / "shared" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "web.shared.accounts.context_processors.navigation",
                "web.shared.context_processors.party",
            ],
        },
    },
]

WSGI_APPLICATION = "web.shared.wsgi.application"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": f"django.contrib.auth.password_validation.{name}"}
    for name in (
        "UserAttributeSimilarityValidator",
        "MinimumLengthValidator",
        "CommonPasswordValidator",
        "NumericPasswordValidator",
    )
]

LANGUAGE_CODE = "en"
TIME_ZONE = "Europe/Brussels"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "web" / "shared" / "static"]
# WhiteNoise serves web/shared/static/ through the finders, as checked out: no collectstatic.
WHITENOISE_USE_FINDERS = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "login"
