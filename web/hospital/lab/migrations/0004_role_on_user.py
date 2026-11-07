from typing import ClassVar

from django.db import migrations
from django.db.migrations.operations.base import Operation

# Each LaboratoryStaffMember record becomes its user's role; undone, the user's username names it.
TO_ROLE = (
    "UPDATE accounts_user SET role = 'laboratory_staff'"
    " WHERE id IN (SELECT user_id FROM lab_laboratorystaffmember)"
)
FROM_ROLE = (
    "INSERT INTO lab_laboratorystaffmember (user_id, name)"
    " SELECT id, username FROM accounts_user WHERE role = 'laboratory_staff'"
)


class Migration(migrations.Migration):
    dependencies: ClassVar[list[tuple[str, str]]] = [
        ("lab", "0003_practice_certificate_name"),
        ("accounts", "0002_user_role"),
    ]
    run_before: ClassVar[list[tuple[str, str]]] = [("accounts", "0003_one_per_role")]

    operations: ClassVar[list[Operation]] = [
        migrations.RunSQL(TO_ROLE, FROM_ROLE),
        migrations.DeleteModel(name="LaboratoryStaffMember"),
    ]
