"""The hospital's messaging endpoint: JSON over plain HTTP in the demo, which
leaves out the report's mutual TLS (web/messaging/schemas.py,
features/messaging.feature).

Its own URLconf: in a deployment its own server serves it, on a network name
only the practices reach, and the pages' server never does (web/settings.py)."""

from typing import Annotated

from django.http import HttpRequest
from django.urls import path
from django.utils import timezone
from ninja import NinjaAPI, Query, Status

from web.lab.models import LabOrder, LabOrderDetails
from web.messaging import schemas
from web.vocabulary import Test

# No browser pages here: the schema only, at openapi.json.
api = NinjaAPI(title="Laboratory", urls_namespace="messaging", docs_url=None)

type Practice = Annotated[str, Query(min_length=1, max_length=100)]


@api.post("lab-orders/", response={204: None})
def send_lab_order(request: HttpRequest, lab_order: schemas.LabOrder) -> Status[None]:
    """Record a lab order once, however often it arrives."""
    LabOrder.objects.record(
        practice=lab_order.practice,
        details=LabOrderDetails(**lab_order.model_dump(exclude={"practice"})),
    )
    return Status(204, None)


@api.get("lab-reports/", response=list[schemas.LabReport])
def fetch_new_lab_reports(
    request: HttpRequest, practice: Practice
) -> list[schemas.LabReport]:
    """The practice's released lab reports it has not acknowledged yet."""
    return [
        schemas.LabReport(
            report_id=lab_order.pk,
            sample_id=lab_order.sample.sample_id,
            test=Test(lab_order.test),
            results=lab_order.results or {},
            ferritin_suggested=lab_order.ferritin_suggested,
            released_at=lab_order.analysed_at,
        )
        for lab_order in LabOrder.objects.reports_to_send(practice)
        if lab_order.analysed_at is not None
    ]


@api.post("lab-reports/acknowledge/", response={204: None})
def acknowledge_lab_reports(
    request: HttpRequest, acknowledgement: schemas.Acknowledgement
) -> Status[None]:
    LabOrder.objects.acknowledge(
        practice=acknowledgement.practice,
        report_ids=acknowledgement.report_ids,
        now=timezone.now(),
    )
    return Status(204, None)


urlpatterns = [path("", api.urls)]
