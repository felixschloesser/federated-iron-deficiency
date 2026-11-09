"""Settings every party's web app shares. Each party's own module
(web/<party>/settings.py, chosen by DJANGO_SETTINGS_MODULE) adds its apps, roles,
pages and data folder. DEBUG is on only with DJANGO_DEBUG=1. The apps serve plain
HTTP: the demo leaves out TLS."""

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

# The roles that log in to this web app. Each party's module sets them, and each
# role logs in to exactly one party (tests/quality/security/test_boundaries.py).
ROLES: list[Role] = []
# The party's name, shown on its pages and sent as its identity when it calls
# another party. Without PARTY_NAME (outside the demo) it is "Demo", a name no
# other party knows.
PARTY_NAME = os.environ.get("PARTY_NAME") or "Demo"


def data_dir(party: str) -> Path:
    """Return the party's data folder, creating it if needed. Everything the
    party stores lives there. It is DATA_DIR if set (demo/README.md), else
    .data/<party>/ in the checkout, so each worktree keeps its own."""
    folder = Path(os.environ.get("DATA_DIR") or BASE_DIR / ".data" / party)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def databases(folder: Path) -> dict[str, Any]:
    return {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": folder / "web.sqlite3",
            # Two processes write this file: the web app and its gRPC endpoint.
            # IMMEDIATE takes the write lock at BEGIN, so the second process
            # waits for the lock instead of failing on its first write.
            "OPTIONS": {"transaction_mode": "IMMEDIATE"},
            # The test database is a file, not in memory: Django never closes an
            # in-memory database, so the gRPC endpoint's threads would leave
            # their connections open in tests.
            "TEST": {"NAME": folder / "test-web.sqlite3"},
        }
    }


def secret_key(folder: Path) -> str:
    """Return DJANGO_SECRET_KEY if set, else a key generated once and kept in the
    party's folder."""
    if key := os.environ.get("DJANGO_SECRET_KEY"):
        return key
    path = folder / ".secret_key"
    if not path.exists():
        path.write_text(get_random_secret_key())
        path.chmod(0o600)
    return path.read_text().strip()


def cookie_names(folder: Path) -> tuple[str, str]:
    """Name the session and CSRF cookies after the party's folder.

    Browsers share cookies between the ports of one host, and the demo serves
    every party from 127.0.0.1. With Django's default names, logging in to one
    party would replace another party's session and CSRF token, and that
    party's next form would fail with a 403."""
    return f"sessionid-{folder.name}", f"csrftoken-{folder.name}"


# The vendored Pico theme in the party's primary colour, so the parties' pages
# look different at a glance. Without PRIMARY_COLOUR, Pico's default theme; a
# colour with no vendored theme is a configuration error.
PICO_DIR = BASE_DIR / "web" / "shared" / "static" / "css" / "vendor" / "pico-2.1.1"
PRIMARY_COLOUR = os.environ.get("PRIMARY_COLOUR") or None
if (
    PRIMARY_COLOUR is not None
    and not (PICO_DIR / f"pico.{PRIMARY_COLOUR}.min.css").is_file()
):
    raise ImproperlyConfigured(
        f"PRIMARY_COLOUR {PRIMARY_COLOUR!r} has no Pico theme in {PICO_DIR}."
    )


# ".localhost" matches localhost and each <party>.localhost the demo's proxy routes (RFC 6761).
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", ".localhost,127.0.0.1").split(
    ","
)

# The apps every party installs; each party's module adds its own.
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
    # Serves the static files when DEBUG is off, which Django itself does not.
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
# WhiteNoise serves web/shared/static/ straight from the finders, so collectstatic is never needed.
WHITENOISE_USE_FINDERS = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "login"
