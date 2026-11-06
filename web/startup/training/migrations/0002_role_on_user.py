from typing import ClassVar

from django.db import migrations
from django.db.migrations.operations.base import Operation

# Each DataScientist record becomes its user's role; undone, the user's username names it.
TO_ROLE = (
    "UPDATE accounts_user SET role = 'data_scientist'"
    " WHERE id IN (SELECT user_id FROM training_datascientist)"
)
FROM_ROLE = (
    "INSERT INTO training_datascientist (user_id, name)"
    " SELECT id, username FROM accounts_user WHERE role = 'data_scientist'"
)


class Migration(migrations.Migration):
    dependencies: ClassVar[list[tuple[str, str]]] = [
        ("training", "0001_initial"),
        ("accounts", "0002_user_role"),
    ]
    run_before: ClassVar[list[tuple[str, str]]] = [("accounts", "0003_one_per_role")]

    operations: ClassVar[list[Operation]] = [
        migrations.RunSQL(TO_ROLE, FROM_ROLE),
        migrations.DeleteModel(name="DataScientist"),
    ]
