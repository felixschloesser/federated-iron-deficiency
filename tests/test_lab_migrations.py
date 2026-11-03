"""Stored lab orders keep only what the laboratory may know (R4, R5, R25)."""

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def _back_to_the_latest() -> Iterator[None]:
    """The database the later tests share ends at the newest migrations again,
    whichever they are, not at AFTER."""
    yield
    executor = MigrationExecutor(connection)
    executor.migrate(executor.loader.graph.leaf_nodes())


BEFORE = ("lab", "0006_screening_model_wording")
AFTER = ("lab", "0007_screened_indication")


def test_stored_lab_orders_keep_whether_the_indication_was_screened_never_which() -> (
    None
):
    executor = MigrationExecutor(connection)
    executor.migrate([BEFORE])
    old = executor.loader.project_state([BEFORE]).apps
    sample_model = old.get_model("lab", "Sample")
    lab_order_model = old.get_model("lab", "LabOrder")
    # (indication, not-screened reason) as the laboratory stored them before.
    stored = {
        "1": ("suspected_ibs", None),
        "2": ("start_of_pregnancy", "indication"),
        "3": ("unexplained_fatigue", "age"),
        "4": ("suspected_anaemia", "no_deployed_model"),
    }
    for sample_id, (indication, reason) in stored.items():
        sample = sample_model._default_manager.create(client="p", sample_id=sample_id)
        lab_order_model._default_manager.create(
            sample=sample,
            test="cbc",
            indication=indication,
            not_screened_reason=reason,
            registered_sex="female",
            age=30,
            general_practitioner="Dr. A",
            ordered_at=datetime(2026, 11, 2, 9, tzinfo=UTC),
        )

    executor = MigrationExecutor(connection)
    executor.migrate([AFTER])
    new = executor.loader.project_state([AFTER]).apps
    after = {
        row["sample__sample_id"]: (
            row["screened_indication"],
            row["not_screened_reason"],
        )
        for row in new.get_model("lab", "LabOrder")._default_manager.values(
            "sample__sample_id", "screened_indication", "not_screened_reason"
        )
    }
    assert after == {
        "1": (True, None),
        "2": (False, "not_eligible"),
        "3": (True, "not_eligible"),
        # A model problem stays: lab staff act on it (O3).
        "4": (True, "no_deployed_model"),
    }
