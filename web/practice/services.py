"""Placing orders."""

from datetime import datetime

from django.core.exceptions import ValidationError
from django.db import transaction

from web.practice.models import GP, ClinicalIndication, Order, Patient, Test


@transaction.atomic
def place_order(
    *,
    gp: GP,
    patient: Patient,
    test: Test,
    indication: ClinicalIndication | None,
    now: datetime,
) -> Order:
    """Order one test for one of the GP's patients (R1, R13)."""
    errors: dict[str, ValidationError] = {}
    if patient.gp_id != gp.pk:
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
    if errors:
        raise ValidationError(errors)
    return Order.objects.create(
        patient=patient,
        test=test,
        indication=indication,
        registered_sex=patient.registered_sex,
        age=patient.age,
        ordered_at=now,
    )
