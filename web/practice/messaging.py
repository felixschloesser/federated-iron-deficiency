"""The general practitioner's app as client of each laboratory it works with: lab
orders out, lab reports in (web/messaging/schemas.py, features/messaging.feature)."""

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import ProxyHandler, Request, build_opener

from django.conf import settings
from pydantic import ValidationError

from web.messaging import schemas
from web.practice.models import Laboratory, LabReport, Order
from web.vocabulary import RegisteredSex, Test

TIMEOUT_SECONDS = 10
# Sending from an order's own request: the general practitioner is waiting.
IN_REQUEST_TIMEOUT_SECONDS = 2
# Straight to the hospital, never through a proxy the environment names.
_OPENER = build_opener(ProxyHandler({}))


def exchange(
    laboratory: Laboratory,
    path: str,
    *,
    message: schemas.Message | None = None,
    query: dict[str, str] | None = None,
    timeout: float = TIMEOUT_SECONDS,
) -> Any:
    """Send one message to the hospital's endpoint, a POST, or with none ask it,
    a GET; return its JSON answer, None if empty. Plain HTTP, as the demo leaves
    out the report's mutual TLS. Raises OSError: HTTPError when the hospital
    refuses, another when the network fails (unreachable)."""
    url = f"http://{laboratory.address}/{path}"
    if query is not None:
        url += f"?{urlencode(query)}"
    request = Request(
        url,
        data=None if message is None else message.model_dump_json().encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with _OPENER.open(request, timeout=timeout) as response:
            answer = response.read()
    except HTTPError as refusal:
        # Its connection closed; its status code stays.
        refusal.close()
        raise
    return json.loads(answer) if answer else None


def unreachable(error: OSError) -> bool:
    """Whether a failed exchange is the network's: wait it out. An HTTP error the
    hospital answered with, which waiting does not mend."""
    return not isinstance(error, HTTPError)


def lab_order(order: Order) -> schemas.LabOrder:
    """An order's lab order: no name, no values. Not checked here: the hospital
    checks every message, and says what it refuses."""
    return schemas.LabOrder.model_construct(
        practice=settings.PARTY_NAME,
        sample_id=order.sample.sample_id,
        test=Test(order.test),
        screened_indication=order.screened_indication,
        registered_sex=RegisteredSex(order.registered_sex),
        age=order.age,
        ordered_at=order.ordered_at,
    )


def send_lab_order(
    order: Order, laboratory: Laboratory, *, timeout: float = TIMEOUT_SECONDS
) -> None:
    """Send an order's lab order (DF23); the laboratory records it once."""
    exchange(laboratory, "lab-orders/", message=lab_order(order), timeout=timeout)


def send_pending_lab_orders(
    laboratory: Laboratory,
    *,
    now: datetime,
    timeout: float = TIMEOUT_SECONDS,
) -> int:
    """Send the laboratory the lab orders of its samples it has not confirmed yet."""
    pending = Order.objects.filter(
        sent_at__isnull=True, sample__laboratory=laboratory
    ).select_related("sample__patient")
    for order in pending:
        send_lab_order(order, laboratory, timeout=timeout)
        Order.objects.filter(pk=order.pk).update(sent_at=now)
    return len(pending)


def check_for_lab_reports(laboratory: Laboratory, *, now: datetime) -> int:
    """Send the laboratory its pending lab orders, fetch its new lab reports (DF25),
    store and acknowledge them."""
    send_pending_lab_orders(laboratory, now=now)
    answer = exchange(
        laboratory, "lab-reports/", query={"practice": settings.PARTY_NAME}
    )
    stored = [
        report.report_id
        for report in _lab_reports(answer)
        if _store(report, laboratory, now=now)
    ]
    if stored:
        exchange(
            laboratory,
            "lab-reports/acknowledge/",
            message=schemas.Acknowledgement(
                practice=settings.PARTY_NAME, report_ids=stored
            ),
        )
    return len(stored)


def _lab_reports(answer: Any) -> list[schemas.LabReport]:
    """The lab reports in the hospital's answer that pass the schema. The hospital
    is another party: one that does not stays unacknowledged instead of holding
    back the others."""
    reports = []
    for item in answer if isinstance(answer, list) else []:
        try:
            reports.append(schemas.LabReport.model_validate(item))
        except ValidationError:
            continue
    return reports


def _store(report: schemas.LabReport, laboratory: Laboratory, *, now: datetime) -> bool:
    """Store a lab report of one of this app's orders on a sample that went to this
    laboratory; False if it matches none: a laboratory reports only on the samples
    it was sent."""
    order = Order.objects.filter(
        sample__sample_id=report.sample_id,
        sample__laboratory=laboratory,
        test=report.test,
    ).first()
    if order is None:
        return False
    LabReport.objects.get_or_create(
        order=order,
        defaults={
            "results": report.results,
            "ferritin_suggested": report.ferritin_suggested,
            "released_at": report.released_at,
            "fetched_at": now,
        },
    )
    return True


@dataclass(frozen=True)
class Check:
    """One check for lab reports at every laboratory the practice works with."""

    asked: int
    fetched: int
    failures: list[tuple[Laboratory, OSError]]


def check_every_laboratory(*, now: datetime) -> Check:
    """Check each laboratory in turn; one that fails holds back no other (features/messaging.feature)."""
    asked, fetched, failures = 0, 0, []
    for laboratory in Laboratory.objects.order_by("name"):
        asked += 1
        try:
            fetched += check_for_lab_reports(laboratory, now=now)
        except OSError as error:
            failures.append((laboratory, error))
    return Check(asked=asked, fetched=fetched, failures=failures)
