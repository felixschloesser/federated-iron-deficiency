"""Logging in and the start page of each role."""

import pytest
from django.test import Client
from django.urls import resolve, reverse
from pytest_django.asserts import assertContains

from tests.conftest import make_general_practitioner
from web.accounts.models import User
from web.accounts.roles import Role, role_of

pytestmark = pytest.mark.django_db
PASSWORD = "check-pass-2026"


def test_role_of_a_general_practitioner() -> None:
    assert (
        role_of(make_general_practitioner("Dr. Demo A").user)
        is Role.GENERAL_PRACTITIONER
    )


def test_role_of_laboratory_staff() -> None:
    from tests.conftest import make_laboratory_staff_member

    assert (
        role_of(make_laboratory_staff_member("Lab One").user) is Role.LABORATORY_STAFF
    )


@pytest.mark.parametrize("role", list(Role))
def test_every_navigation_link_of_a_role_resolves(role: Role) -> None:
    assert role.nav_links()
    for link in role.nav_links():
        assert resolve(link["url"])


def test_role_of_a_laboratory_director() -> None:
    from tests.conftest import make_laboratory_director

    director = make_laboratory_director("Director One")
    assert role_of(director.user) is Role.LABORATORY_DIRECTOR


def test_role_of_an_account_without_one() -> None:
    assert role_of(User.objects.create_user(username="no-role")) is None


@pytest.mark.parametrize("role", list(Role))
def test_every_role_has_a_start_page(role: Role) -> None:
    assert resolve(role.start_url())


def test_login_leads_to_the_start_page_of_the_role(client: Client) -> None:
    user = make_general_practitioner("Dr. Demo A").user
    user.set_password(PASSWORD)
    user.save()
    response = client.post(
        reverse("login"), {"username": user.username, "password": PASSWORD}
    )
    assert response["Location"] == reverse("home")
    assert client.get(reverse("home"))["Location"] == reverse("practice:patients")


def test_account_without_a_role_cannot_log_in(client: Client) -> None:
    User.objects.create_user(username="no-role", password=PASSWORD)
    response = client.post(
        reverse("login"), {"username": "no-role", "password": PASSWORD}
    )
    assert response.status_code == 200
    errors = response.context["form"].errors.as_data()
    assert [error.code for error in errors["__all__"]] == ["no_role"]
    assert "_auth_user_id" not in client.session


def test_a_wrong_password_marks_both_fields_invalid(client: Client) -> None:
    """Pico draws aria-invalid fields red; which field was wrong is not told."""
    User.objects.create_user(username="someone", password=PASSWORD)
    response = client.post(
        reverse("login"), {"username": "someone", "password": "wrong"}
    )
    errors = response.context["form"].errors.as_data()
    assert [error.code for error in errors["__all__"]] == ["invalid_login"]
    assertContains(response, 'aria-invalid="true"', count=2)
    # The form's error summary is the kit's error alert.
    assertContains(response, '<article role="alert" data-level="error"')


def test_login_labels_have_no_trailing_colon(client: Client) -> None:
    """The kit's labels read as names, not as prompts: "Username", not "Username:"."""
    response = client.get(reverse("login"))
    assertContains(response, '<label for="id_username">Username</label>')
    assertContains(response, '<label for="id_password">Password</label>')
