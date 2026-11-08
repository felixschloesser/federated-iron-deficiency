"""Scenarios: lab orders in and lab reports out, practice by practice
(features/hospital/lab_orders.feature), against TestRequest.objects; the gRPC
endpoint around them is tests/hospital/test_messaging.py."""

from datetime import UTC, datetime

import pytest
from django.core.exceptions import ValidationError
from pytest_bdd import given, parsers, scenarios, then, when

from tests.conftest import World
from web.hospital.analyser.models import Participant
from web.hospital.lab.models import LabOrderDetails, Practice, Sample, TestRequest
from web.shared.vocabulary import ClinicalIndication, RegisteredSex
from web.shared.vocabulary import Test as OrderedTest

NOW = datetime(2026, 10, 30, 10, 0, tzinfo=UTC)
pytestmark = pytest.mark.django_db

scenarios("hospital/lab_orders.feature")


@given(parsers.parse('hospital "{name}" knows practices "{first}" and "{second}"'))
def knows_practices(name: str, first: str, second: str) -> None:
    for practice in (first, second):
        Practice.objects.add(name=practice)


def receive(practice: str, sample_id: str, test: OrderedTest) -> TestRequest:
    return TestRequest.objects.receive(
        practice=Practice.objects.get(name=practice),
        details=LabOrderDetails(
            sample_id=sample_id,
            test=test,
            clinical_indication=ClinicalIndication.SUSPECTED_ANAEMIA
            if test.takes_indication()
            else None,
            registered_sex=RegisteredSex.FEMALE,
            age=32,
            ordered_at=NOW,
        ),
    )


SENDS = (
    r'practice "(?P<practice>[^"]+)" (?:sends|sent) a lab order for a CBC'
    r' on sample "(?P<sample_id>[^"]+)"$'
)


@when(parsers.re(SENDS))
@given(parsers.re(SENDS))
def sends(practice: str, sample_id: str) -> None:
    receive(practice, sample_id, OrderedTest.CBC)


@given(
    parsers.parse(
        '"{name}" released a lab report on sample "{sample_id}"'
        ' of practice "{practice}"'
    )
)
def released(name: str, sample_id: str, practice: str) -> None:
    Participant.objects.create(seqn=int(sample_id.split("-")[0]), cbc={})
    receive(practice, sample_id, OrderedTest.FERRITIN).run_analyser(
        directory=None, now=NOW
    )


@when(
    parsers.parse(
        'practice "{practice}" acknowledges the lab report on sample "{sample_id}"'
    )
)
def acknowledges(practice: str, sample_id: str) -> None:
    TestRequest.objects.acknowledge(
        practice=Practice.objects.get(name=practice),
        report_ids=[TestRequest.objects.get(sample__sample_id=sample_id).pk],
        now=NOW,
    )


def fetched(practice: str) -> list[str]:
    known = Practice.objects.get(name=practice)
    return [
        test_request.sample.sample_id
        for test_request in TestRequest.objects.reports_to_send(known)
    ]


@then(
    parsers.parse(
        'practice "{practice}" fetches the lab report on sample "{sample_id}"'
    )
)
def fetches_report(practice: str, sample_id: str) -> None:
    assert fetched(practice) == [sample_id]


@then(parsers.parse('practice "{practice}" fetches no lab reports'))
def fetches_none(practice: str) -> None:
    assert fetched(practice) == []


@then(parsers.parse('"{name}" has one test request on sample "{sample_id}"'))
def one_test_request(name: str, sample_id: str) -> None:
    assert TestRequest.objects.filter(sample__sample_id=sample_id).count() == 1


@then(parsers.parse('"{name}" has two samples with sample ID "{sample_id}"'))
def two_samples(name: str, sample_id: str) -> None:
    assert Sample.objects.filter(sample_id=sample_id).count() == 2


@when(parsers.parse('hospital "{name}" registers practice "{practice}"'))
def registers(world: World, name: str, practice: str) -> None:
    try:
        Practice.objects.add(name=practice)
    except ValidationError as error:
        world["refused"] = error


@then("registering is refused as a slug taken")
def refused_slug_taken(world: World) -> None:
    refused = world["refused"].error_dict.values()
    assert [error.code for errors in refused for error in errors] == ["slug_taken"]
    assert Practice.objects.count() == 2
