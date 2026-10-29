"""What laboratory staff see: rows that hold no patient field (R14)."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from django.db.models import F, QuerySet

from web.lab.models import Sample
from web.practice.models import ClinicalIndication, Order, RegisteredSex, Test

# The only order fields that reach the laboratory, by row alias: never the patient.
ORDER_FIELDS = {
    "row_order": "pk",
    "row_test": "test",
    "row_indication": "indication",
    "row_sex": "registered_sex",
    "row_age": "age",
    "row_general_practitioner": "patient__general_practitioner__name",
}
SAMPLE_FIELDS = {
    "row_sample": "pk",
    "row_sample_id": "sample_id",
    "row_received_at": "received_at",
    "row_analysed_at": "analysed_at",
    "row_results": "results",
}


@dataclass(frozen=True)
class LabRow:
    order: int
    test: str
    indication: str | None
    registered_sex: str
    age: int
    general_practitioner: str
    sample: int | None = None
    sample_id: str | None = None
    received_at: datetime | None = None
    analysed_at: datetime | None = None
    results: dict[str, float] | None = None


def _row(values: Mapping[str, Any]) -> LabRow:
    indication = values["row_indication"]
    return LabRow(
        order=values["row_order"],
        test=Test(values["row_test"]).label,
        indication=None if indication is None else ClinicalIndication(indication).label,
        registered_sex=RegisteredSex(values["row_sex"]).label,
        age=values["row_age"],
        general_practitioner=values["row_general_practitioner"],
        sample=values.get("row_sample"),
        sample_id=values.get("row_sample_id"),
        received_at=values.get("row_received_at"),
        analysed_at=values.get("row_analysed_at"),
        results=values.get("row_results"),
    )


def _sample_rows(samples: QuerySet[Sample]) -> list[LabRow]:
    fields = {
        **{alias: F(path) for alias, path in SAMPLE_FIELDS.items()},
        **{alias: F(f"order__{path}") for alias, path in ORDER_FIELDS.items()},
    }
    return [_row(values) for values in samples.values(**fields)]


def orders_to_receive() -> list[LabRow]:
    """Orders whose sample the laboratory has not received yet."""
    orders = Order.objects.filter(sample__isnull=True).order_by("ordered_at", "pk")
    fields = {alias: F(path) for alias, path in ORDER_FIELDS.items()}
    return [_row(values) for values in orders.values(**fields)]


def samples_to_analyse() -> list[LabRow]:
    """Received samples the analyser has not run on yet."""
    samples = Sample.objects.filter(analysed_at__isnull=True)
    return _sample_rows(samples.order_by("received_at", "pk"))


def samples_analysed() -> list[LabRow]:
    """Samples with results, newest first."""
    samples = Sample.objects.filter(analysed_at__isnull=False)
    return _sample_rows(samples.order_by("-analysed_at", "-pk"))
