"""Two processes write one party's SQLite file: the web app, and the messaging
endpoint or the check for lab reports."""

import sqlite3
import threading
from datetime import UTC, datetime

import pytest
from django.db import connection

pytestmark = [pytest.mark.subprocess, pytest.mark.django_db(transaction=True)]

# Long enough for the service to reach its write while the other process holds the lock.
OTHER_COMMITS_AFTER_SECONDS = 1.0


def test_a_write_waits_for_the_other_process_instead_of_failing() -> None:
    from tests.hospital.conftest import make_practice
    from web.hospital.lab.models import LabOrder, LabOrderDetails
    from web.vocabulary import RegisteredSex, Test

    practice = make_practice()
    other = sqlite3.connect(
        connection.settings_dict["NAME"], isolation_level=None, check_same_thread=False
    )
    # The other process is in the middle of a write: it holds the lock until it commits.
    other.execute("BEGIN")
    other.execute("UPDATE django_migrations SET app = app")
    commit = threading.Timer(OTHER_COMMITS_AFTER_SECONDS, other.execute, ["COMMIT"])
    commit.start()
    try:
        LabOrder.objects.receive(
            practice=practice,
            details=LabOrderDetails(
                sample_id="135318-1",
                test=Test.CBC,
                screened_indication=True,
                registered_sex=RegisteredSex.FEMALE,
                age=30,
                ordered_at=datetime(2026, 11, 2, 9, tzinfo=UTC),
            ),
        )
    finally:
        commit.join()
        other.close()

    assert LabOrder.objects.count() == 1
