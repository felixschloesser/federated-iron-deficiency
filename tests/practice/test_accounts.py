"""Logging in, as every party's web app does (shared.accounts, shared; checked
here, in the practice's run), and the practice's role and its pages."""

import pytest
from django.conf import settings
from django.test import Client
from django.urls import resolve, reverse
from pytest_bdd import given, parsers, scenario, then, when
from pytest_django.asserts import assertContains, assertNotContains

from shared.accounts.forms import RoleAuthenticationForm
from shared.accounts.models import User
from shared.accounts.roles import Role, role_of
from tests.practice.conftest import make_general_practitioner

pytestmark = pytest.mark.django_db
PASSWORD = "check-pass-2026"


def test_role_of_a_general_practitioner() -> None:
    assert role_of(make_general_practitioner("Dr. Demo A")) is Role.GENERAL_PRACTITIONER


def test_role_of_an_account_without_one() -> None:
    assert role_of(User.objects.create_user(username="no-role")) is None


def test_login_leads_to_the_start_page_of_the_role(client: Client) -> None:
    user = make_general_practitioner("Dr. Demo A")
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
    # One form-wide error: the kit's error alert says just that, plainly.
    assertContains(response, '<article role="alert" data-level="error"')
    assertContains(response, "<p>Wrong username or password.</p>")
    assertNotContains(response, "There is a problem")
    assertNotContains(response, "case-sensitive")


def test_login_labels_have_no_trailing_colon(client: Client) -> None:
    """The kit's labels read as names, not as prompts: "Username", not "Username:"."""
    response = client.get(reverse("login"))
    assertContains(response, '<label for="id_username">Username</label>')
    assertContains(response, '<label for="id_password">Password</label>')


def test_a_refused_login_focuses_only_its_error(client: Client) -> None:
    """HTML allows one autofocus: the error, not the username field."""
    User.objects.create_user(username="someone", password=PASSWORD)
    response = client.post(
        reverse("login"), {"username": "someone", "password": "wrong"}
    )
    assertContains(response, "autofocus", count=1)


@pytest.mark.parametrize("role", settings.ROLES)
def test_each_role_of_this_party_has_its_pages_here(role: Role) -> None:
    """The role's start page and header links are this party's own: none points
    at another party's pages, which its URLconf does not serve."""
    assert resolve(role.start_url())
    assert role.nav_links()
    for link in role.nav_links():
        assert resolve(link["url"])


@scenario(
    "practice/access.feature",
    "An account whose role is another party's cannot log in here",
)
def test_an_account_whose_role_is_another_partys_cannot_log_in_here() -> None:
    pass


@given(parsers.parse('an account "{username}" of {role}'))
def account(username: str, role: str) -> None:
    by_label = {choice.label: choice for choice in Role}
    User.objects.create_user(username=username, password=PASSWORD, role=by_label[role])


@when(
    parsers.parse('"{username}" logs in to the practice\'s web app'),
    target_fixture="login",
)
def logs_in(username: str) -> RoleAuthenticationForm:
    form = RoleAuthenticationForm(data={"username": username, "password": PASSWORD})
    form.is_valid()
    return form


@then(parsers.parse('logging in is refused with code "{code}"'))
def refused(login: RoleAuthenticationForm, code: str) -> None:
    assert [error.code for error in login.errors.as_data().get("__all__", [])] == [code]


def test_a_logged_in_account_of_another_partys_role_gets_403_not_a_crash(
    client: Client,
) -> None:
    """Its start page is another party's, which this URLconf cannot reverse: once
    a 500, now refused like an account without a role."""
    staff = User.objects.create_user(username="staff", role=Role.LABORATORY_STAFF)
    client.force_login(staff)
    assert client.get(reverse("home")).status_code == 403
    assert client.get(reverse("practice:patients")).status_code == 403
