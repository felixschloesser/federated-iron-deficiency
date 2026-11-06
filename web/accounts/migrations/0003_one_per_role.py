from typing import ClassVar

from django.db import migrations, models
from django.db.migrations.operations.base import Operation


class Migration(migrations.Migration):
    """After the role records are gone: their constraints' names are free."""

    dependencies: ClassVar[list[tuple[str, str]]] = [("accounts", "0002_user_role")]

    operations: ClassVar[list[Operation]] = [
        migrations.AddConstraint(
            model_name="user",
            constraint=models.UniqueConstraint(
                condition=models.Q(("role", "general_practitioner")),
                fields=("role",),
                name="one_general_practitioner",
                violation_error_code="one_general_practitioner",
                violation_error_message="A practice has one general practitioner.",
            ),
        ),
        migrations.AddConstraint(
            model_name="user",
            constraint=models.UniqueConstraint(
                condition=models.Q(("role", "laboratory_director")),
                fields=("role",),
                name="one_laboratory_director",
                violation_error_code="one_laboratory_director",
                violation_error_message="A hospital has one laboratory director.",
            ),
        ),
    ]
