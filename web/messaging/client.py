"""The general practitioner's side: sending lab orders (DF1)."""

from web.lab import services as hospital
from web.practice.models import Order
from web.vocabulary import ClinicalIndication, RegisteredSex, Test


def send_lab_order(order: Order) -> None:
    """Send the lab order of an order to the general practitioner's hospital (R22).

    shortcut: delivered by a direct call while both run in one process; gRPC with
    mutual TLS replaces it when the two kinds of deployment split.
    """
    hospital.record_lab_order(
        sample_id=order.sample_id,
        test=Test(order.test),
        indication=ClinicalIndication(order.indication) if order.indication else None,
        registered_sex=RegisteredSex(order.registered_sex),
        age=order.age,
        general_practitioner=order.patient.general_practitioner.name,
        ordered_at=order.ordered_at,
    )
