"""Settings for one hospital's deployment, secure unless DJANGO_DEBUG=1."""

import os
from pathlib import Path

import django_stubs_ext
from django.core.exceptions import ImproperlyConfigured
from django.core.management.utils import get_random_secret_key

from web.party import Party

# Lets generic views be subscripted (ListView[Order]) at runtime, as mypy wants.
django_stubs_ext.monkeypatch()

BASE_DIR = Path(__file__).resolve().parent.parent

DEBUG = os.environ.get("DJANGO_DEBUG") == "1"

# One deployment per party: what it stores lives in its own folder (spec §9, R21).
HOSPITAL_DIR = (
    Path(os.environ["HOSPITAL_DIR"]) if "HOSPITAL_DIR" in os.environ else None
)
PRACTICE_DIR = (
    Path(os.environ["PRACTICE_DIR"]) if "PRACTICE_DIR" in os.environ else None
)
if HOSPITAL_DIR is not None and PRACTICE_DIR is not None:
    raise ImproperlyConfigured("Set HOSPITAL_DIR or PRACTICE_DIR, not both.")
PARTY_DIR = HOSPITAL_DIR or PRACTICE_DIR
# None: a development checkout, serving every party's pages from one database.
PARTY = (
    Party.HOSPITAL
    if HOSPITAL_DIR
    else Party.GENERAL_PRACTITIONER
    if PRACTICE_DIR
    else None
)
# The hospital's final models (R16); without HOSPITAL_DIR, an optional folder.
FINAL_MODELS_DIR = (
    HOSPITAL_DIR / "final-models"
    if HOSPITAL_DIR
    else Path(os.environ["FINAL_MODELS_DIR"])
    if "FINAL_MODELS_DIR" in os.environ
    else None
)
# Shown in the title bar and header; never the screening's name.
PARTY_NAME = (
    os.environ.get("PRACTICE_NAME", "Demo practice")
    if PRACTICE_DIR
    else os.environ.get("HOSPITAL_NAME", "Demo hospital")
)
if PARTY_DIR is not None and "DATABASE_NAME" in os.environ:
    raise ImproperlyConfigured(
        "DATABASE_NAME cannot be set with HOSPITAL_DIR or PRACTICE_DIR:"
        " the database lives in that folder."
    )
# The hospital's messaging endpoint; the practice is always the client (R23).
MESSAGING_ADDRESS = os.environ.get("MESSAGING_ADDRESS")
if MESSAGING_ADDRESS is not None and PRACTICE_DIR is None:
    raise ImproperlyConfigured("MESSAGING_ADDRESS needs PRACTICE_DIR.")


def _secret_key() -> str:
    """Return the key from the environment, else one kept per checkout."""
    if key := os.environ.get("DJANGO_SECRET_KEY"):
        return key
    path = (PARTY_DIR or BASE_DIR) / ".secret_key"
    if not path.exists():
        path.write_text(get_random_secret_key())
        path.chmod(0o600)
    return path.read_text().strip()


SECRET_KEY = _secret_key()

ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "web.accounts",
    *(app for party in ([PARTY] if PARTY else Party) for app in party.apps()),
]

AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = ["web.accounts.backends.RoleBackend"]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "web.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "web.accounts.context_processors.navigation",
                "web.context_processors.party",
            ],
        },
    },
]

WSGI_APPLICATION = "web.wsgi.application"

# One SQLite file per worktree, named after it, so no two share a database.
DATABASE_NAME = os.environ.get("DATABASE_NAME", BASE_DIR.name)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": PARTY_DIR / "web.sqlite3"
        if PARTY_DIR
        else BASE_DIR / f"{DATABASE_NAME}.sqlite3",
        # A file, not memory: Django never closes an in-memory database, so the
        # messaging endpoint's threads would leave their connections open in tests.
        "TEST": {"NAME": BASE_DIR / f"test-{DATABASE_NAME}.sqlite3"},
    }
}

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
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "login"

SECURE_SSL_REDIRECT = not DEBUG
SECURE_HSTS_SECONDS = 0 if DEBUG else 60 * 60 * 24 * 365
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
