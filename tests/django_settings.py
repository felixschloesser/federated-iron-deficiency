"""What every party's in-process tests run with: each party's conftest offers
this fixture, so only runs with Django settings use it."""

import copy

import pytest
from pytest_django.fixtures import Settings


class MissingVariable(str):
    """Fails the render that would have shown a missing variable as blank."""

    def __mod__(self, name: object) -> str:
        raise AssertionError(f"Template variable missing: {name}")


@pytest.fixture(autouse=True)
def _test_settings(settings: Settings) -> None:
    settings.SECURE_SSL_REDIRECT = False
    # Assign a copy, so Django rebuilds its template engines and restores them after.
    templates = copy.deepcopy(settings.TEMPLATES)
    templates[0]["OPTIONS"]["string_if_invalid"] = MissingVariable("%s")
    settings.TEMPLATES = templates
