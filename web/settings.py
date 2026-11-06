"""Settings for one party's web app; DEBUG only with DJANGO_DEBUG=1. Plain
HTTP: the demo leaves out the report's TLS."""

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

# One web app per party: what it stores lives in its own folder (demo/README.md, features/quality/party_isolation.feature).
# Without PARTY: a development checkout, serving every party's pages from one database.
try:
    PARTY: Party | None = Party(os.environ["PARTY"]) if "PARTY" in os.environ else None
except ValueError:
    raise ImproperlyConfigured(
        f"PARTY is one of {', '.join(party.value for party in Party)}."
    ) from None
if PARTY is not None and "DATA_DIR" not in os.environ:
    raise ImproperlyConfigured("PARTY needs DATA_DIR, the folder for its data.")
DATA_DIR = Path(os.environ["DATA_DIR"]) if PARTY is not None else None
# The hospital's screening models (features/final_models.feature); in development, an optional folder.
SCREENING_MODELS_DIR: Path | None = (
    Path(os.environ["SCREENING_MODELS_DIR"])
    if "SCREENING_MODELS_DIR" in os.environ
    else None
)
# The startup's copy of every final model (features/startup/training.feature); in
# development, an optional folder.
FINAL_MODELS_DIR: Path | None = (
    Path(os.environ["FINAL_MODELS_DIR"]) if "FINAL_MODELS_DIR" in os.environ else None
)
if DATA_DIR is not None and PARTY is Party.HOSPITAL:
    SCREENING_MODELS_DIR = DATA_DIR / "screening-models"
if DATA_DIR is not None and PARTY is Party.STARTUP:
    FINAL_MODELS_DIR = DATA_DIR / "final-models"
# Shown in the title bar and header; never the screening's name. A development
# checkout shows the hospital's.
PARTY_NAME = os.environ.get("PARTY_NAME") or (PARTY or Party.HOSPITAL).demo_name()
# The name the hospitals issued this practice and know it by, which its app
# sends in every message (glossary.toml, certificate name).
PRACTICE_CERTIFICATE_NAME = os.environ.get("PRACTICE_CERTIFICATE_NAME", "demo-practice")
# A Pico colour theme per party, so its pages are told apart at a glance; absent:
# Pico's default. Only a vendored theme will do.
PICO_DIR = BASE_DIR / "web" / "static" / "css" / "vendor" / "pico-2.1.1"
PARTY_COLOUR = os.environ.get("PARTY_COLOUR") or None
if (
    PARTY_COLOUR is not None
    and not (PICO_DIR / f"pico.{PARTY_COLOUR}.min.css").is_file()
):
    raise ImproperlyConfigured(
        f"PARTY_COLOUR {PARTY_COLOUR!r} has no Pico theme in {PICO_DIR}."
    )
if DATA_DIR is not None and "DATABASE_NAME" in os.environ:
    raise ImproperlyConfigured(
        "DATABASE_NAME cannot be set with DATA_DIR: the database lives in that folder."
    )


def _secret_key() -> str:
    """Return the key from the environment, else one kept per checkout."""
    if key := os.environ.get("DJANGO_SECRET_KEY"):
        return key
    path = (DATA_DIR or BASE_DIR) / ".secret_key"
    if not path.exists():
        path.write_text(get_random_secret_key())
        path.chmod(0o600)
    return path.read_text().strip()


SECRET_KEY = _secret_key()

# ".localhost": localhost and each <party>.localhost the demo's proxy routes (RFC 6761).
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", ".localhost,127.0.0.1").split(
    ","
)

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

ROOT_URLCONF = "web.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "web" / "templates"],
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
        "NAME": DATA_DIR / "web.sqlite3"
        if DATA_DIR
        else BASE_DIR / f"{DATABASE_NAME}.sqlite3",
        # Two processes write this file (the web app, and messaging): take the write
        # lock at BEGIN, so the second waits instead of failing on its first write.
        "OPTIONS": {"transaction_mode": "IMMEDIATE"},
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
STATICFILES_DIRS = [BASE_DIR / "web" / "static"]
# WhiteNoise serves web/static/ through the finders, as checked out: no collectstatic.
WHITENOISE_USE_FINDERS = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "login"

# Browsers share cookies between ports of one host, and the demo serves every
# party from 127.0.0.1: without its own names, one party's login would replace
# another's session and CSRF token (a 403 on its next form).
if DATA_DIR is not None:
    SESSION_COOKIE_NAME = f"sessionid-{DATA_DIR.name}"
    CSRF_COOKIE_NAME = f"csrftoken-{DATA_DIR.name}"
