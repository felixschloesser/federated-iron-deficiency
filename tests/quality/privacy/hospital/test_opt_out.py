"""A past patient's control over whether her record trains a model (the
report's issue C: U3)."""

import pytest

from ml.cohort import CBC_VARS
from tests.hospital.conftest import make_lab_records
from web.hospital.cohort.models import LabRecord

# The field issue C adds; named here, as LabRecord does not have it yet.
OPTED_OUT = "opted_out"


@pytest.mark.django_db
@pytest.mark.privacy_issue
def test_an_opted_out_lab_record_never_reaches_the_training_cohort() -> None:
    """Threat U3 (issue C). Pass: a lab record marked OPTED_OUT is left out of
    the training cohort, and every other eligible record is in it."""
    make_lab_records(120, iron_deficient=20)
    opted_out = LabRecord.objects.order_by("pk").first()
    assert opted_out is not None
    LabRecord.objects.filter(pk=opted_out.pk).update(**{OPTED_OUT: True})

    cohort = LabRecord.objects.training_cohort()
    first_value = CBC_VARS[0]
    assert opted_out.cbc[first_value] not in set(cohort[first_value])
    assert len(cohort) == 119
