from typing import ClassVar

from django.db import migrations
from django.db.migrations.operations.base import Operation

# Each GeneralPractitioner record becomes its user's role; undone, the user's username names it.
TO_ROLE = (
    "UPDATE accounts_user SET role = 'general_practitioner'"
    " WHERE id IN (SELECT user_id FROM practice_generalpractitioner)"
)
FROM_ROLE = (
    "INSERT INTO practice_generalpractitioner (user_id, name)"
    " SELECT id, username FROM accounts_user WHERE role = 'general_practitioner'"
)


class Migration(migrations.Migration):
    dependencies: ClassVar[list[tuple[str, str]]] = [
        ("practice", "0006_patient_no_general_practitioner"),
        ("accounts", "0002_user_role"),
    ]
    run_before: ClassVar[list[tuple[str, str]]] = [("accounts", "0003_one_per_role")]

    operations: ClassVar[list[Operation]] = [
        migrations.RunSQL(TO_ROLE, FROM_ROLE),
        migrations.DeleteModel(name="GeneralPractitioner"),
    ]
