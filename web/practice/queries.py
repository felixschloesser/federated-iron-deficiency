"""What the general practitioner is offered, decided from the recorded facts."""

from web.practice.models import LabReport
from web.vocabulary import Test


def ferritin_order_offered(lab_report: LabReport) -> bool:
    """Order ferritin beside a suggestion, until its sample has ferritin (R11, R26)."""
    sample = lab_report.order.sample
    return (
        lab_report.ferritin_suggested
        and not sample.orders.filter(test=Test.FERRITIN).exists()
    )
