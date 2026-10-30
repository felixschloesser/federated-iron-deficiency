"""What the general practitioner is offered, decided from the recorded facts."""

from web.practice.models import LabReport
from web.vocabulary import Test


def ferritin_order_offered(lab_report: LabReport) -> bool:
    """Order ferritin beside a suggestion, until the patient has ferritin (R11, R26)."""
    patient = lab_report.order.patient
    return (
        lab_report.ferritin_suggested
        and not patient.orders.filter(test=Test.FERRITIN).exists()
    )
