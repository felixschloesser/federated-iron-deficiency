from typing import ClassVar

from django.conf import settings
from django.db import migrations, models
from django.db.migrations.operations.base import Operation


class Migration(migrations.Migration):
    dependencies: ClassVar[list[tuple[str, str]]] = [
        ("practice", "0005_order_rules_as_constraints"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations: ClassVar[list[Operation]] = [
        migrations.AddConstraint(
            model_name="generalpractitioner",
            constraint=models.UniqueConstraint(
                models.Value(1),
                name="one_general_practitioner",
                violation_error_code="one_general_practitioner",
                violation_error_message="A practice has one general practitioner.",
            ),
        ),
    ]
