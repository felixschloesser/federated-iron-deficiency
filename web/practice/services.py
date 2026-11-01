"""Placing orders."""

from datetime import datetime

from django.core.exceptions import ValidationError
from django.db import transaction

from web.practice.models import GeneralPractitioner, Order, Patient, Sample
from web.vocabulary import ClinicalIndication, Test


@transaction.atomic
def place_order(
    *,
    general_practitioner: GeneralPractitioner,
    patient: Patient,
    test: Test,
    indication: ClinicalIndication | None,
    now: datetime,
) -> Order:
    """Collect a new sample from one of the general practitioner's patients and
    order one test on it (R1, R13, R26)."""
    errors = order_errors(general_practitioner, patient, test, indication)
    if errors:
        raise ValidationError(errors)
    sample = Sample.objects.create(
        patient=patient, sample_id=patient.next_sample_id(), collected_at=now
    )
    return create_order(sample, test, indication, now)


@transaction.atomic
def order_on_sample(
    *,
    general_practitioner: GeneralPractitioner,
    sample: Sample,
    test: Test,
    indication: ClinicalIndication | None,
    now: datetime,
) -> Order:
    """Order one more test on a sample the laboratory holds, such as ferritin
    beside a suggestion (R2, R11, R26)."""
    errors = order_errors(general_practitioner, sample.patient, test, indication)
    if sample.orders.filter(test=test).exists():
        errors["test"] = ValidationError(
            "This sample already has this test.", code="already_ordered"
        )
    if errors:
        raise ValidationError(errors)
    return create_order(sample, test, indication, now)


def order_errors(
    general_practitioner: GeneralPractitioner,
    patient: Patient,
    test: Test,
    indication: ClinicalIndication | None,
) -> dict[str, ValidationError]:
    """What refuses an order on any sample: one error per failing condition."""
    errors: dict[str, ValidationError] = {}
    if patient.general_practitioner_id != general_practitioner.pk:
        errors["patient"] = ValidationError(
            "This is not one of your patients.", code="not_your_patient"
        )
    if test.takes_indication() and indication is None:
        errors["indication"] = ValidationError(
            "A CBC needs a clinical indication.", code="indication_required"
        )
    if not test.takes_indication() and indication is not None:
        errors["indication"] = ValidationError(
            "Ferritin takes no clinical indication.", code="indication_not_applicable"
        )
    return errors


def create_order(
    sample: Sample, test: Test, indication: ClinicalIndication | None, now: datetime
) -> Order:
    """The order, copying the patient's registered sex and age (R1, R14)."""
    return Order.objects.create(
        sample=sample,
        test=test,
        indication=indication,
        registered_sex=sample.patient.registered_sex,
        age=sample.patient.age,
        ordered_at=now,
    )
