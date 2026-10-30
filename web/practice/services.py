"""Placing orders."""

from datetime import datetime

from django.core.exceptions import ValidationError
from django.db import transaction

from web.messaging.client import send_lab_order
from web.practice.models import GeneralPractitioner, Order, Patient
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
    """Order one test for one of the general practitioner's patients (R1, R13, R26)."""
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
    if patient.orders.filter(test=test).exists():
        errors["test"] = ValidationError(
            "This patient already has this test; a sample is tested once per test.",
            code="already_ordered",
        )
    if errors:
        raise ValidationError(errors)
    order = Order.objects.create(
        patient=patient,
        test=test,
        indication=indication,
        registered_sex=patient.registered_sex,
        age=patient.age,
        sample_id=patient.sample_id,
        ordered_at=now,
    )
    send_lab_order(order)
    return order
