"""Scenarios: analysing samples, and the lab never seeing a patient's name
(features/hospital/lab.feature). Only the hospital's side: lab orders arrive as its
lab-order endpoint records them."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse
from pytest_bdd import given, parsers, scenarios, then, when

from ml.cohort import CBC_VARS
from tests.conftest import World
from tests.hospital.conftest import make_practice, make_tube, receive_lab_order
from web.hospital.analyser.models import FERRITIN, Participant
from web.hospital.lab.models import Sample, ScreeningResult, TestRequest
from web.shared.vocabulary import ClinicalIndication, RegisteredSex
from web.shared.vocabulary import Test as OrderedTest

NOW = datetime(2026, 10, 29, 10, 0, tzinfo=UTC)
TESTS = {"CBC": OrderedTest.CBC, "ferritin": OrderedTest.FERRITIN}
pytestmark = pytest.mark.django_db

scenarios("hospital/lab.feature")


def tube(world: World, patient: str) -> Participant:
    """What the patient's latest sample, or the next one, measures at the
    hospital's analyser stand-in: the participant its sample ID names."""
    return Participant.objects.get(seqn=world["patients"][patient]["seqn"])


def place(world: World, test: str, patient: str) -> None:
    """A new sample of the patient arriving with its lab order, under its own
    sample ID: a later sample of the patient names another participant."""
    record = world["patients"][patient]
    if record["samples"]:
        record["seqn"] = make_tube().seqn
    record["samples"] += 1
    world["test_request"] = receive_lab_order(
        str(record["seqn"]),
        TESTS[test],
        NOW,
        sex=record["sex"],
        age=record["age"],
    )


@given(
    parsers.parse(
        'practice "{practice}" sends samples of patient "{patient}",'
        " registered sex {sex}, aged {age:d}"
    )
)
def practice_sends_samples(
    world: World, practice: str, patient: str, sex: str, age: int
) -> None:
    make_practice()
    world["patients"][patient] = {
        "seqn": make_tube().seqn,
        "sex": RegisteredSex(sex),
        "age": age,
        "samples": 0,
    }


@given(
    parsers.parse('"{patient}" has NHANES CBC values and ferritin {ferritin:g} ng/mL')
)
def nhanes_values(world: World, patient: str, ferritin: float) -> None:
    participant = tube(world, patient)
    participant.cbc = {var: float(index) for index, var in enumerate(CBC_VARS, 1)}
    participant.ferritin = ferritin
    participant.save()


@given(parsers.re(r'a (?P<test>CBC|ferritin) order for "(?P<patient>[^"]+)"$'))
def an_order(world: World, test: str, patient: str) -> None:
    place(world, test, patient)


@given("a ferritin order on that sample")
def ferritin_on_that_sample(world: World) -> None:
    analysed = world["test_request"]
    world["test_request"] = receive_lab_order(
        analysed.sample.sample_id,
        OrderedTest.FERRITIN,
        NOW,
        sex=RegisteredSex(analysed.registered_sex),
        age=analysed.age,
    )


@given(
    parsers.re(r'an analysed (?P<test>CBC|ferritin) sample for "(?P<patient>[^"]+)"')
)
def an_analysed_sample(world: World, test: str, patient: str) -> None:
    place(world, test, patient)
    world["test_request"].run_analyser(directory=None, now=NOW)


@given(
    parsers.parse('the analyser stand-in has no values for the sample of "{patient}"')
)
def no_tube(world: World, patient: str) -> None:
    tube(world, patient).delete()


@when("laboratory staff run the analyser")
def run_analyser(world: World, tmp_path: Path) -> None:
    test_request = TestRequest.objects.get(pk=world["test_request"].pk)
    try:
        world["test_request"] = test_request.run_analyser(directory=tmp_path, now=NOW)
    except ValidationError as error:
        world["error"] = error


PAGES = {"first": 0, "second": 1}


@given("laboratory staff opened the CBC order on two pages")
def two_pages(world: World) -> None:
    """Two copies of the lab order as loaded, like two open tabs or two staff."""
    world["pages"] = [
        TestRequest.objects.get(pk=world["test_request"].pk) for _ in PAGES
    ]


@when(parsers.parse("laboratory staff run the analyser from the {page} page"))
def run_analyser_from(world: World, page: str) -> None:
    number = PAGES[page]
    try:
        world["pages"][number].run_analyser(
            directory=None,
            now=NOW + timedelta(minutes=number),
        )
    except ValidationError as error:
        world["error"] = error


@then("the CBC order keeps the analysis from the first page")
def keeps_first_analysis(world: World) -> None:
    assert TestRequest.objects.get(pk=world["test_request"].pk).analysed_at == NOW


@then(parsers.parse('{action} is refused with code "{code}"'))
def refused(world: World, action: str, code: str) -> None:
    assert world["error"].code == code


@then(parsers.parse('the sample has the 13 NHANES CBC values of "{patient}"'))
def sample_has_cbc(world: World, patient: str) -> None:
    test_request = world["test_request"]
    assert test_request.results == tube(world, patient).cbc
    assert len(test_request.results) == 13
    assert test_request.analysed_at == NOW


@then(parsers.re(r"the (?P<test>CBC|ferritin) order is ready to analyse"))
def ready_to_analyse(world: World, test: str) -> None:
    assert world["test_request"].test == TESTS[test]
    assert world["test_request"] in TestRequest.objects.to_analyse()


@then(parsers.re(r"its sample is (?P<negated>not )?a stored sample"))
def stored_sample(world: World, negated: str | None) -> None:
    (row,) = [
        row
        for row in TestRequest.objects.to_analyse()
        if row.pk == world["test_request"].pk
    ]
    assert row.stored_sample is (negated is None)


@then(parsers.parse("the sample has ferritin {ferritin:g} ng/mL"))
def sample_has_ferritin(world: World, ferritin: float) -> None:
    assert world["test_request"].results == {FERRITIN: ferritin}


@then(
    "the lab's samples hold sample ID, registered sex, age, test, clinical"
    " indication and results, and no general practitioner"
)
def lab_rows_hold(world: World) -> None:
    (test_request,) = TestRequest.objects.to_analyse()
    assert test_request.sample.sample_id == world["test_request"].sample.sample_id
    # The practice, by its name, stands for its one general practitioner.
    fields = {field.name for field in TestRequest._meta.fields}
    assert not {"general_practitioner", "name", "patient"} & fields
    assert test_request.get_registered_sex_display() == "Female"
    assert test_request.get_test_display() == "CBC"
    assert test_request.clinical_indication == ClinicalIndication.SUSPECTED_ANAEMIA


@then("the lab's records relate to nothing outside the hospital")
def lab_relates_to_the_hospital_only(world: World) -> None:
    # So no lab query can reach a general practitioner's records, and with them
    # a patient's name.
    for model in (Sample, TestRequest):
        related = {
            field.related_model._meta.app_label
            for field in model._meta.get_fields()
            if field.related_model is not None
        }
        assert related <= {"lab", "deployment"}, (model, related)


@given("no screening model is deployed")
def no_model_deployed(world: World) -> None:
    from web.hospital.deployment.models import Deployment

    assert not Deployment.objects.exists()


@when("laboratory staff run the analyser on the To analyse page")
def run_on_page(world: World, client: Client) -> None:
    from tests.hospital.conftest import make_laboratory_staff_member

    client.force_login(make_laboratory_staff_member("Lab One"))
    world["client"] = client
    world["response"] = client.post(
        reverse("lab:analyse", kwargs={"pk": world["test_request"].pk}),
        follow=True,
    )


@then(
    "they are told the lab report was released without screening, and to tell the"
    " laboratory director"
)
def told_to_tell_director(world: World) -> None:
    sample_id = world["test_request"].sample.sample_id
    messages = [str(message) for message in world["response"].context["messages"]]
    expected = (
        f"Sample {sample_id}: CBC analysed, lab report released without screening."
        " Tell the laboratory director."
    )
    assert messages == [expected]


@then("the Analysed page shows the CBC and no screening result")
def analysed_shows_no_screening(world: World) -> None:
    response = world["client"].get(reverse("lab:analysed"))
    page = response.content.decode()
    assert world["test_request"].sample.sample_id in page
    assert "Screening result" not in page
    for label in ScreeningResult.labels:
        assert label not in page, label
