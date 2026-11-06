"""The startup's builders."""

from typing import TYPE_CHECKING

from tests.conftest import make_user

if TYPE_CHECKING:
    from web.accounts.models import User


def make_data_scientist(name: str) -> "User":
    from web.accounts.roles import Role

    return make_user(name, Role.DATA_SCIENTIST)
