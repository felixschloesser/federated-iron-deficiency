"""Recording lab orders, receiving samples and running the analyser."""

from dataclasses import dataclass
from datetime import datetime

from django.core.exceptions import ValidationError
from django.db import transaction

from web.lab.models import LabOrder, Sample
from web.nhanes.models import Participant
from web.vocabulary import ClinicalIndication, RegisteredSex, Test


@dataclass(frozen=True)
class LabOrderDetails:
    """What a lab order (DF1) says: no patient name, no values (R25)."""

    sample_id: str
    test: Test
    indication: ClinicalIndication | None
    registered_sex: RegisteredSex
    age: int
    general_practitioner: str
    ordered_at: datetime


@transaction.atomic
def record_lab_order(*, client: str, details: LabOrderDetails) -> LabOrder:
    """Record a lab order (DF1) from `client` once, however often it arrives (R22, O18)."""
    sample, _ = Sample.objects.get_or_create(client=client, sample_id=details.sample_id)
    lab_order, _ = LabOrder.objects.get_or_create(
        sample=sample,
        test=details.test,
        defaults={
            "indication": details.indication,
            "registered_sex": details.registered_sex,
            "age": details.age,
            "general_practitioner": details.general_practitioner,
            "ordered_at": details.ordered_at,
        },
    )
    return lab_order


@transaction.atomic
def receive(*, sample: Sample, now: datetime) -> Sample:
    """Register that a sample's tube arrived in the laboratory (R2)."""
    if sample.received_at is not None:
        raise ValidationError(
            "This sample has already been received.", code="already_received"
        )
    sample.received_at = now
    sample.save(update_fields=["received_at"])
    return sample


@transaction.atomic
def run_analyser(*, lab_order: LabOrder, now: datetime) -> LabOrder:
    """Record what the analyser measures on the stored sample for the test (R3, R12)."""
    if lab_order.analysed_at is not None:
        raise ValidationError(
            "This test has already been analysed.", code="already_analysed"
        )
    # The tube's contents: the NHANES participant whose number is the sample ID.
    tube = Participant.objects.get(seqn=int(lab_order.sample.sample_id))
    lab_order.results = tube.measure(Test(lab_order.test))
    lab_order.analysed_at = now
    lab_order.save(update_fields=["results", "analysed_at"])
    return lab_order


@transaction.atomic
def acknowledge_lab_reports(
    *, client: str, report_ids: list[int], now: datetime
) -> None:
    """`client` has these lab reports of its own: hand them out no more."""
    LabOrder.objects.filter(
        sample__client=client, pk__in=report_ids, report_acknowledged_at__isnull=True
    ).update(report_acknowledged_at=now)
