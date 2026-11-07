"""Scenarios: lab orders in and lab reports out, practice by practice
(features/hospital/lab_orders.feature), against TestRequest.objects; the gRPC
endpoint around them is tests/hospital/test_messaging.py."""

from datetime import UTC, datetime

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from hospital.analyser.models import Participant
from hospital.lab.models import LabOrderDetails, Practice, Sample, TestRequest
from shared.vocabulary import RegisteredSex
from shared.vocabulary import Test as OrderedTest

NOW = datetime(2026, 10, 30, 10, 0, tzinfo=UTC)
pytestmark = pytest.mark.django_db

scenarios("hospital/lab_orders.feature")


@given(parsers.parse('hospital "{name}" knows practices "{first}" and "{second}"'))
def knows_practices(name: str, first: str, second: str) -> None:
    for certificate_name in (first, second):
        Practice.objects.add(certificate_name=certificate_name, name=certificate_name)


def receive(certificate_name: str, sample_id: str, test: OrderedTest) -> TestRequest:
    return TestRequest.objects.receive(
        practice=Practice.objects.get(certificate_name=certificate_name),
        details=LabOrderDetails(
            sample_id=sample_id,
            test=test,
            screened_indication=test.takes_indication(),
            registered_sex=RegisteredSex.FEMALE,
            age=32,
            ordered_at=NOW,
        ),
    )


SENDS = (
    r'practice "(?P<certificate_name>[^"]+)" (?:sends|sent) a lab order for a CBC'
    r' on sample "(?P<sample_id>[^"]+)"$'
)


@when(parsers.re(SENDS))
@given(parsers.re(SENDS))
def sends(certificate_name: str, sample_id: str) -> None:
    receive(certificate_name, sample_id, OrderedTest.CBC)


@given(
    parsers.parse(
        '"{name}" released a lab report on sample "{sample_id}"'
        ' of practice "{certificate_name}"'
    )
)
def released(name: str, sample_id: str, certificate_name: str) -> None:
    Participant.objects.create(seqn=int(sample_id.split("-")[0]), cbc={})
    receive(certificate_name, sample_id, OrderedTest.FERRITIN).run_analyser(
        directory=None, now=NOW
    )


@when(
    parsers.parse(
        'practice "{certificate_name}" acknowledges the lab report'
        ' on sample "{sample_id}"'
    )
)
def acknowledges(certificate_name: str, sample_id: str) -> None:
    TestRequest.objects.acknowledge(
        practice=Practice.objects.get(certificate_name=certificate_name),
        report_ids=[TestRequest.objects.get(sample__sample_id=sample_id).pk],
        now=NOW,
    )


def fetched(certificate_name: str) -> list[str]:
    practice = Practice.objects.get(certificate_name=certificate_name)
    return [
        test_request.sample.sample_id
        for test_request in TestRequest.objects.reports_to_send(practice)
    ]


@then(
    parsers.parse(
        'practice "{certificate_name}" fetches the lab report on sample "{sample_id}"'
    )
)
def fetches_report(certificate_name: str, sample_id: str) -> None:
    assert fetched(certificate_name) == [sample_id]


@then(parsers.parse('practice "{certificate_name}" fetches no lab reports'))
def fetches_none(certificate_name: str) -> None:
    assert fetched(certificate_name) == []


@then(parsers.parse('"{name}" has one test request on sample "{sample_id}"'))
def one_test_request(name: str, sample_id: str) -> None:
    assert TestRequest.objects.filter(sample__sample_id=sample_id).count() == 1


@then(parsers.parse('"{name}" has two samples with sample ID "{sample_id}"'))
def two_samples(name: str, sample_id: str) -> None:
    assert Sample.objects.filter(sample_id=sample_id).count() == 2
