"""Settings for one hospital's deployment, secure unless DJANGO_DEBUG=1."""

import os
from pathlib import Path

import django_stubs_ext
from django.core.exceptions import ImproperlyConfigured
from django.core.management.utils import get_random_secret_key

# Lets generic views be subscripted (ListView[Order]) at runtime, as mypy wants.
django_stubs_ext.monkeypatch()

BASE_DIR = Path(__file__).resolve().parent.parent

DEBUG = os.environ.get("DJANGO_DEBUG") == "1"

# One deployment per hospital: what it stores lives in its own folder (spec §9, R21).
HOSPITAL_DIR = (
    Path(os.environ["HOSPITAL_DIR"]) if "HOSPITAL_DIR" in os.environ else None
)
# Shown in the title bar and header; never the screening's name.
HOSPITAL_NAME = os.environ.get("HOSPITAL_NAME", "Demo hospital")
if HOSPITAL_DIR is not None and "DATABASE_NAME" in os.environ:
    raise ImproperlyConfigured(
        "DATABASE_NAME cannot be set with HOSPITAL_DIR: the database lives in HOSPITAL_DIR."
    )


def _secret_key() -> str:
    """Return the key from the environment, else one kept per checkout."""
    if key := os.environ.get("DJANGO_SECRET_KEY"):
        return key
    path = (HOSPITAL_DIR or BASE_DIR) / ".secret_key"
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
    "web.practice",
    "web.nhanes",
    "web.lab",
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
                "web.context_processors.hospital",
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
        "NAME": HOSPITAL_DIR / "web.sqlite3"
        if HOSPITAL_DIR
        else BASE_DIR / f"{DATABASE_NAME}.sqlite3",
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
