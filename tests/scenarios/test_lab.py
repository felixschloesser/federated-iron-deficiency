"""Scenarios: analysing samples (features/lab.feature), and the
lab never seeing a patient's name (features/access.feature)."""

from datetime import UTC, datetime, timedelta

import pytest
from django.core.exceptions import ValidationError
from pytest_bdd import given, parsers, scenario, scenarios, then, when

from iron_deficiency.cohort import CBC_VARS
from tests.conftest import World, collect_and_order, deliver, suggest_ferritin_on
from web.lab.models import LabOrder, Sample
from web.nhanes.models import FERRITIN, Participant
from web.practice.models import GeneralPractitioner, Patient
from web.vocabulary import ClinicalIndication
from web.vocabulary import Test as OrderedTest

NOW = datetime(2026, 10, 29, 10, 0, tzinfo=UTC)
TESTS = {"CBC": OrderedTest.CBC, "ferritin": OrderedTest.FERRITIN}
pytestmark = pytest.mark.django_db

scenarios("lab.feature")


@scenario("access.feature", "The lab never sees a patient's name")
def test_the_lab_never_sees_a_patients_name() -> None:
    pass


def tube(patient: Patient) -> Participant:
    """What the patient's tube would measure, at the hospital's analyser stand-in."""
    return Participant.objects.get(seqn=int(patient.nhanes_number))


def place(world: World, test: str, patient: str) -> None:
    ordered = TESTS[test]
    indication = (
        ClinicalIndication.UNEXPLAINED_FATIGUE if ordered.takes_indication() else None
    )
    record = world["patients"][patient]
    world["order"] = collect_and_order(
        general_practitioner=GeneralPractitioner.objects.get(),
        patient=record,
        test=ordered,
        indication=indication,
        now=NOW,
    )
    world["lab_order"] = deliver(world["order"])


@given(
    parsers.parse('"{patient}" has NHANES CBC values and ferritin {ferritin:g} ng/mL')
)
def nhanes_values(world: World, patient: str, ferritin: float) -> None:
    participant = tube(world["patients"][patient])
    participant.cbc = {var: float(index) for index, var in enumerate(CBC_VARS, 1)}
    participant.ferritin = ferritin
    participant.save()


@given(parsers.parse('patient "{patient}" of "{owner}" without NHANES ferritin'))
def patient_without_ferritin(world: World, patient: str, owner: str) -> None:
    from tests.conftest import make_patient
    from web.vocabulary import RegisteredSex

    world["patients"][patient] = make_patient(patient, RegisteredSex.FEMALE, 30)


@given(parsers.re(r'a (?P<test>CBC|ferritin) order for "(?P<patient>[^"]+)"$'))
def an_order(world: World, test: str, patient: str) -> None:
    place(world, test, patient)


@given("a ferritin order on that sample")
def ferritin_on_that_sample(world: World) -> None:
    sample = world["order"].sample
    suggest_ferritin_on(sample, NOW)
    world["order"] = GeneralPractitioner.objects.get().place_order(
        sample=sample,
        test=OrderedTest.FERRITIN,
        indication=None,
        now=NOW,
    )
    world["lab_order"] = deliver(world["order"])


@given(
    parsers.re(r'an analysed (?P<test>CBC|ferritin) sample for "(?P<patient>[^"]+)"')
)
def an_analysed_sample(world: World, test: str, patient: str) -> None:
    place(world, test, patient)
    world["lab_order"].run_analyser(directory=None, now=NOW)


@given(
    parsers.parse('the analyser stand-in has no values for the sample of "{patient}"')
)
def no_tube(world: World, patient: str) -> None:
    from web.nhanes.models import Participant

    seqn = int(world["patients"][patient].nhanes_number)
    Participant.objects.filter(seqn=seqn).delete()


@when("laboratory staff run the analyser")
def run_analyser(world: World) -> None:
    lab_order = LabOrder.objects.get(pk=world["lab_order"].pk)
    try:
        world["lab_order"] = lab_order.run_analyser(directory=None, now=NOW)
    except ValidationError as error:
        world["error"] = error


PAGES = {"first": 0, "second": 1}


@given("laboratory staff opened the CBC order on two pages")
def two_pages(world: World) -> None:
    """Two copies of the lab order as loaded, like two open tabs or two staff."""
    world["pages"] = [LabOrder.objects.get(pk=world["lab_order"].pk) for _ in PAGES]


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
    assert LabOrder.objects.get(pk=world["lab_order"].pk).analysed_at == NOW


@then(parsers.parse('{action} is refused with code "{code}"'))
def refused(world: World, action: str, code: str) -> None:
    assert world["error"].code == code


@then(parsers.parse('the sample has the 13 NHANES CBC values of "{patient}"'))
def sample_has_cbc(world: World, patient: str) -> None:
    lab_order = world["lab_order"]
    assert lab_order.results == tube(world["patients"][patient]).cbc
    assert len(lab_order.results) == 13
    assert lab_order.analysed_at == NOW


@then(parsers.re(r"the (?P<test>CBC|ferritin) order is ready to analyse"))
def ready_to_analyse(world: World, test: str) -> None:
    assert world["lab_order"].test == TESTS[test]
    assert world["lab_order"] in LabOrder.objects.to_analyse()


@then(parsers.re(r"its sample is (?P<negated>not )?a stored sample"))
def stored_sample(world: World, negated: str | None) -> None:
    (row,) = [
        row for row in LabOrder.objects.to_analyse() if row.pk == world["lab_order"].pk
    ]
    assert row.stored_sample is (negated is None)


@then(parsers.parse("the sample has ferritin {ferritin:g} ng/mL"))
def sample_has_ferritin(world: World, ferritin: float) -> None:
    assert world["lab_order"].results == {FERRITIN: ferritin}


@then("the sample's ferritin is not available in the demo data")
def ferritin_not_available(world: World) -> None:
    assert world["lab_order"].analysed_at == NOW
    assert world["lab_order"].results == {}


@then(
    "the lab's samples hold sample ID, registered sex, age, test, whether the"
    " indication is screened and results, and no general practitioner"
)
def lab_rows_hold(world: World) -> None:
    (lab_order,) = LabOrder.objects.to_analyse()
    assert lab_order.sample.sample_id == world["order"].sample.sample_id
    # The practice, by its name, stands for its one general practitioner.
    assert "general_practitioner" not in {field.name for field in LabOrder._meta.fields}
    assert "Dr. Demo A" not in str(vars(lab_order))
    assert lab_order.get_registered_sex_display() == "Female"
    assert lab_order.get_test_display() == "CBC"
    # Ordered for unexplained fatigue: screened, which is all the lab learns of it.
    assert lab_order.screened_indication is True


@then("no lab query returns the patient's name")
def no_patient_name(world: World) -> None:
    # The lab's models have no relation to the general practitioner's records.
    for model in (Sample, LabOrder):
        related = {field.related_model for field in model._meta.get_fields()}
        assert not related & {Patient}, model
    for lab_order in LabOrder.objects.to_analyse():
        assert "Test Patient" not in str(vars(lab_order))
