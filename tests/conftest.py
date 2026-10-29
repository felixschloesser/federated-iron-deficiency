"""Shared givens for the scenarios, and builders for the view tests."""

from typing import TYPE_CHECKING, Any

import pytest
from pytest_bdd import given, parsers

# The models are imported inside the builders too, so a missing app fails only
# the tests that use it.
if TYPE_CHECKING:
    from web.practice.models import GP, Patient, RegisteredSex

World = dict[str, Any]


@pytest.fixture
def world() -> World:
    """What the steps of one scenario have built so far, by name."""
    return {"gps": {}, "patients": {}}


def make_gp(name: str) -> "GP":
    from django.contrib.auth.models import User
    from web.practice.models import GP

    user = User.objects.create_user(username=name.lower().replace(" ", "-"))
    return GP.objects.create(user=user, name=name)


def make_patient(gp: "GP", name: str, sex: "RegisteredSex", age: int) -> "Patient":
    from web.practice.models import Patient

    return Patient.objects.create(gp=gp, name=name, registered_sex=sex, age=age)


@given(
    parsers.re(
        r'GP "(?P<gp>[^"]+)" with patient "(?P<patient>[^"]+)"'
        r"(?:, registered sex (?P<sex>\w+), aged (?P<age>\d+))?$"
    )
)
def gp_with_patient(
    world: World, db: None, gp: str, patient: str, sex: str | None, age: str | None
) -> None:
    from web.practice.models import RegisteredSex

    owner = world["gps"].get(gp) or make_gp(gp)
    world["gps"][gp] = owner
    world["patients"][patient] = make_patient(
        owner, patient, RegisteredSex(sex or "female"), int(age or 30)
    )
