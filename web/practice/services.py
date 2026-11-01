"""Collecting samples and ordering tests on them."""

from datetime import datetime

from django.core.exceptions import ValidationError
from django.db import transaction

from web.practice.models import GeneralPractitioner, Order, Patient, Sample
from web.vocabulary import ClinicalIndication, Test


@transaction.atomic
def collect_sample(
    *, general_practitioner: GeneralPractitioner, patient: Patient, now: datetime
) -> Sample:
    """Record blood collected from one of the general practitioner's patients,
    with the patient's next sample ID; tests are ordered on it afterwards (R26)."""
    if patient.general_practitioner_id != general_practitioner.pk:
        raise ValidationError(
            {
                "patient": ValidationError(
                    "This is not one of your patients.", code="not_your_patient"
                )
            }
        )
    return Sample.objects.create(
        patient=patient, sample_id=patient.next_sample_id(), collected_at=now
    )


@transaction.atomic
def place_order(
    *,
    general_practitioner: GeneralPractitioner,
    sample: Sample,
    test: Test,
    indication: ClinicalIndication | None,
    now: datetime,
) -> Order:
    """Order one test on a collected sample, also a later one such as ferritin
    beside a suggestion (R1, R2, R11, R13, R26)."""
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
