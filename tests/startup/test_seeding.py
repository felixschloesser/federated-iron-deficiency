"""The startup's demo data (seed_startup): its data scientist only."""

import pytest
from django.core.management import call_command
from pytest_django.fixtures import Settings

from shared.accounts.models import User
from shared.accounts.roles import Role, role_of

pytestmark = pytest.mark.django_db


def test_the_startup_seeds_only_its_data_scientist(settings: Settings) -> None:
    settings.DEBUG = True
    call_command("seed_startup")
    assert {role_of(user) for user in User.objects.all()} == {
        Role.DATA_SCIENTIST,
        None,
    }
