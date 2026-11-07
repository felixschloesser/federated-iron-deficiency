"""The startup's demo data (python -m demo.seed startup): its data scientist only."""

import pytest
from pytest_django.fixtures import Settings

from demo.seed import main
from shared.accounts.models import User
from shared.accounts.roles import Role, role_of

pytestmark = pytest.mark.django_db


def test_the_startup_seeds_only_its_data_scientist(settings: Settings) -> None:
    settings.DEBUG = True
    main(["startup"])
    assert {role_of(user) for user in User.objects.all()} == {
        Role.DATA_SCIENTIST,
        None,
    }
