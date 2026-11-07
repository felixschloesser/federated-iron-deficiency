"""The startup's builders."""

from typing import TYPE_CHECKING

from tests.conftest import make_user
from tests.django_settings import _test_settings

if TYPE_CHECKING:
    from web.shared.accounts.models import User

# The settings every test of this party runs with (tests/django_settings.py).
__all__ = ["_test_settings"]


def make_data_scientist(name: str) -> "User":
    from web.shared.accounts.roles import Role

    return make_user(name, Role.DATA_SCIENTIST)
