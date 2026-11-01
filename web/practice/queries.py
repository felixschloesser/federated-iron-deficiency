"""What the general practitioner is offered, decided from the recorded facts."""

from django.db.models import QuerySet

from web.practice.models import GeneralPractitioner, LabReport
from web.vocabulary import Test


def ferritin_order_offered(lab_report: LabReport) -> bool:
    """Order ferritin beside a suggestion, until its sample has ferritin (R11, R26)."""
    sample = lab_report.order.sample
    return (
        lab_report.ferritin_suggested
        and not sample.orders.filter(test=Test.FERRITIN).exists()
    )


def ferritin_suggestions(
    general_practitioner: GeneralPractitioner,
) -> QuerySet[LabReport]:
    """The general practitioner's lab reports suggesting ferritin whose sample has
    no ferritin order yet: what awaits them, newest first (R11)."""
    return (
        LabReport.objects.filter(
            ferritin_suggested=True,
            order__sample__patient__general_practitioner=general_practitioner,
        )
        .exclude(order__sample__orders__test=Test.FERRITIN)
        .select_related("order__sample__patient")
        .order_by("-released_at", "-pk")
    )
