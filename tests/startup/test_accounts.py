"""The startup's role: who logs in to its web app, and where they land."""

import pytest
from django.conf import settings
from django.urls import resolve

from shared.accounts.roles import Role, role_of

pytestmark = pytest.mark.django_db

from tests.startup.conftest import make_data_scientist


def test_role_of_a_data_scientist() -> None:
    assert role_of(make_data_scientist("Data One")) is Role.DATA_SCIENTIST


@pytest.mark.parametrize("role", settings.ROLES)
def test_each_role_of_this_party_has_its_pages_here(role: Role) -> None:
    """The role's start page and header links are this party's own: none points
    at another party's pages, which its URLconf does not serve."""
    assert resolve(role.start_url())
    assert role.nav_links()
    for link in role.nav_links():
        assert resolve(link["url"])
