"""What laboratory staff see: lab orders, which hold no patient field (R14)."""

from __future__ import annotations

from typing import TypedDict

from django.db.models import Exists, OuterRef, QuerySet
from django_stubs_ext import WithAnnotations

from web.lab.models import LabOrder


class StoredSample(TypedDict):
    stored_sample: bool


def lab_orders_to_analyse() -> QuerySet[WithAnnotations[LabOrder, StoredSample]]:
    """Tests the analyser has not run yet. A sample arrives with its lab order; it is
    a stored sample once another test on it has been analysed (R2)."""
    analysed_on_same_sample = LabOrder.objects.filter(
        sample=OuterRef("sample"), analysed_at__isnull=False
    )
    return (
        LabOrder.objects.filter(analysed_at__isnull=True)
        .annotate(stored_sample=Exists(analysed_on_same_sample))
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
