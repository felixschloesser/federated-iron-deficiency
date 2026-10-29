"""Receiving samples and running the analyser."""

from datetime import datetime

from django.core.exceptions import ValidationError
from django.db import transaction

from web.lab.models import Sample
from web.practice.models import Order, Test


@transaction.atomic
def receive(*, order: Order, now: datetime) -> Sample:
    """Register an order's sample in the laboratory and assign its sample ID (R2)."""
    if Sample.objects.filter(order=order).exists():
        raise ValidationError(
            "This order's sample has already been received.", code="already_received"
        )
    sample = Sample.objects.create(order=order, received_at=now)
    sample.sample_id = f"{now:%y%m%d}-{sample.pk:05d}"
    sample.save(update_fields=["sample_id"])
    return sample


@transaction.atomic
def run_analyser(*, sample: Sample, now: datetime) -> Sample:
    """Record what the analyser measures for the sample's test (R3, R12)."""
    if sample.analysed_at is not None:
        raise ValidationError(
            "This sample has already been analysed.", code="already_analysed"
        )
    order = sample.order
    sample.results = order.patient.participant.measure(Test(order.test))
    sample.analysed_at = now
    sample.save(update_fields=["results", "analysed_at"])
    return sample
