"""The hospital's roles: who logs in to its web app, and where they land."""

import pytest
from django.conf import settings
from django.urls import resolve

from web.accounts.roles import Role, role_of

pytestmark = pytest.mark.django_db

from tests.hospital.conftest import (
    make_laboratory_director,
    make_laboratory_staff_member,
)


def test_role_of_laboratory_staff() -> None:
    assert role_of(make_laboratory_staff_member("Lab One")) is Role.LABORATORY_STAFF


def test_role_of_a_laboratory_director() -> None:
    director = make_laboratory_director("Director One")
    assert role_of(director) is Role.LABORATORY_DIRECTOR


@pytest.mark.parametrize("role", settings.ROLES)
def test_each_role_of_this_party_has_its_pages_here(role: Role) -> None:
    """The role's start page and header links are this party's own: none points
    at another party's pages, which its URLconf does not serve."""
    assert resolve(role.start_url())
    assert role.nav_links()
    for link in role.nav_links():
        assert resolve(link["url"])
