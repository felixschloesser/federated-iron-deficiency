"""Examples of privacy tests in the hospital's Django app. Keep, rename under a
threat ID, or delete them."""

from pathlib import Path

import pytest
from django.db import models
from django.utils import timezone

from ml.cohort import FEATURES
from tests.hospital.conftest import (
    found_cohort,
    make_lab_records,
    make_laboratory_director,
)
from web.hospital.cohort.models import LabRecord, TrainingCohort
from web.hospital.lab.models import Sample, TestRequest


@pytest.mark.parametrize(
    ("model", "fields"),
    [
        # Of the patient, only registered sex and age, copied at ordering.
        (
            TestRequest,
            {
                "id",
                "sample",
                "test",
                "clinical_indication",
                "registered_sex",
                "age",
                "ordered_at",
                "analysed_at",
                "results",
                "screening_result",
                "not_screened_reason",
                "screened_by",
                "report_acknowledged_at",
            },
        ),
        (Sample, {"id", "practice", "sample_id"}),
        (
            LabRecord,
            {
                "id",
                "registered_sex",
                "age",
                "cbc",
                "ferritin",
                "crp",
                "clinical_indication",
            },
        ),
    ],
)
def test_the_hospital_stores_nothing_that_names_a_patient(
    model: type[models.Model], fields: set[str]
) -> None:
    """Example. Threat: identifiability at the hospital. Pass: the hospital's
    records about patients have exactly these fields, none naming a patient; a
    new field fails this until it is added here on purpose."""
    assert {field.name for field in model._meta.concrete_fields} == fields


@pytest.mark.django_db
def test_the_training_cohort_holds_no_identifier(tmp_path: Path) -> None:
    """Example. Threat: identifiability in the training cohort the startup's
    code reads (TB4). Pass: a provided training cohort's columns are the CBC
    values, age and the label, nothing else."""
    make_lab_records(120, iron_deficient=20)
    TrainingCohort.objects.provide(
        directory=tmp_path,
        by=make_laboratory_director("director"),
        now=timezone.now(),
    )
    cohort = found_cohort(tmp_path)
    assert cohort is not None
    assert list(cohort.columns) == [*FEATURES, "iron_deficient"]
