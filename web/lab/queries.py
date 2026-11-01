"""What laboratory staff see: lab orders, which hold no patient field (R14)."""

from django.db.models import QuerySet

from web.lab.models import LabOrder


def lab_orders_to_analyse() -> QuerySet[LabOrder]:
    """Tests the analyser has not run yet; each sample arrives with its lab order."""
    return (
        LabOrder.objects.filter(analysed_at__isnull=True)
        .select_related("sample")
        .order_by("ordered_at", "pk")
    )


def lab_orders_analysed() -> QuerySet[LabOrder]:
    """Tests with results, newest first."""
    return (
        LabOrder.objects.filter(analysed_at__isnull=False)
        .select_related("sample")
        .order_by("-analysed_at", "-pk")
    )


def lab_reports_to_send(client: str) -> QuerySet[LabOrder]:
    """`client`'s analysed lab orders it has not acknowledged yet (R23, R24)."""
    return (
        LabOrder.objects.filter(
            sample__client=client,
            analysed_at__isnull=False,
            report_acknowledged_at__isnull=True,
        )
        .select_related("sample")
        .order_by("pk")
    )
