"""Recording lab orders and running the analyser."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from django.core.exceptions import ValidationError
from django.db import transaction

from iron_deficiency.screening import suggests_ferritin
from web.deployment.domain import deployed_model
from web.lab.domain import NotScreened, ScreeningResult
from web.lab.models import LabOrder, Sample
from web.nhanes.models import Participant
from web.vocabulary import ClinicalIndication, RegisteredSex, Test


@dataclass(frozen=True)
class LabOrderDetails:
    """What a lab order (DF24) says: no patient name, no values (R25)."""

    sample_id: str
    test: Test
    indication: ClinicalIndication | None
    registered_sex: RegisteredSex
    age: int
    general_practitioner: str
    ordered_at: datetime


@transaction.atomic
def record_lab_order(*, client: str, details: LabOrderDetails) -> LabOrder:
    """Record a lab order (DF24) from `client` once, however often it arrives (R22, O18)."""
    sample, _ = Sample.objects.get_or_create(client=client, sample_id=details.sample_id)
    lab_order, _ = LabOrder.objects.get_or_create(
        sample=sample,
        test=details.test,
        defaults={
            "indication": details.indication,
            "registered_sex": details.registered_sex,
            "age": details.age,
            "general_practitioner": details.general_practitioner,
            "ordered_at": details.ordered_at,
        },
    )
    return lab_order


@transaction.atomic
def run_analyser(
    *, lab_order: LabOrder, directory: Path | None, now: datetime
) -> LabOrder:
    """Record what the analyser measures on the stored sample for the test (R3, R12),
    screen a CBC with the deployed model in `directory`, and so release its lab
    report at once (R8): the report goes out with the analysis, never before."""
    if lab_order.analysed_at is not None:
        raise ValidationError(
            "This test has already been analysed.", code="already_analysed"
        )
    # The tube's contents: the NHANES participant whose number is the sample ID.
    sample_id = lab_order.sample.sample_id
    tube = (
        Participant.objects.filter(seqn=int(sample_id)).first()
        if sample_id.isdigit()
        else None
    )
    if tube is None:
        raise ValidationError(
            "The analyser has no tube for this sample ID.", code="no_tube"
        )
    lab_order.results = tube.measure(Test(lab_order.test))
    lab_order.analysed_at = now
    if lab_order.test == Test.CBC:
        screen(lab_order, directory)
    lab_order.save(
        update_fields=[
            "results",
            "analysed_at",
            "screening_result",
            "not_screened_reason",
            "screened_by",
        ]
    )
    return lab_order


def screen(lab_order: LabOrder, directory: Path | None) -> None:
    """Set an analysed CBC's screening result: the model's decision, or not
    screened with the first reason (R4, R5, R19). Nothing else of it is kept (R7)."""
    reason = lab_order.not_eligible()
    if reason is None:
        final_model, no_usable_model = deployed_model(directory)
        if no_usable_model is not None:
            reason = NotScreened(no_usable_model)
        elif final_model is not None and directory is not None:
            # shortcut: the file is read again after deployed_model() hashed it; a
            # swap in between goes unseen. Hash and load one copy if that matters.
            suggested = suggests_ferritin(
                lab_order.results or {},
                lab_order.age,
                directory / f"{final_model.run_id}.pt",
            )
            lab_order.screening_result = (
                ScreeningResult.FERRITIN_SUGGESTED
                if suggested
                else ScreeningResult.FERRITIN_NOT_SUGGESTED
            )
            lab_order.screened_by = final_model
            return
    lab_order.screening_result = ScreeningResult.NOT_SCREENED
    lab_order.not_screened_reason = reason


@transaction.atomic
def acknowledge_lab_reports(
    *, client: str, report_ids: list[int], now: datetime
) -> None:
    """`client` has these lab reports of its own: hand them out no more."""
    LabOrder.objects.filter(
        sample__client=client, pk__in=report_ids, report_acknowledged_at__isnull=True
    ).update(report_acknowledged_at=now)
