"""What laboratory staff see: lab orders, which hold no patient field (R14)."""

from django.db.models import QuerySet

from web.lab.models import LabOrder, Sample


def samples_to_receive() -> QuerySet[Sample]:
    """Samples with a lab order whose tube has not arrived yet."""
    return (
        Sample.objects.filter(received_at__isnull=True)
        .prefetch_related("lab_orders")
        .order_by("pk")
    )


def lab_orders_to_analyse() -> QuerySet[LabOrder]:
    """Tests on received samples that the analyser has not run yet."""
    return (
        LabOrder.objects.filter(
            sample__received_at__isnull=False, analysed_at__isnull=True
        )
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
