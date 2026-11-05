from typing import ClassVar

from django.db import migrations, models
from django.db.migrations.operations.base import Operation


class Migration(migrations.Migration):
    dependencies: ClassVar[list[tuple[str, str]]] = [
        ("practice", "0004_laboratory_no_folder")
    ]

    operations: ClassVar[list[Operation]] = [
        migrations.AddField(
            model_name="laboratory",
            name="primary",
            field=models.BooleanField(default=False),
        ),
        migrations.AddConstraint(
            model_name="laboratory",
            constraint=models.UniqueConstraint(
                condition=models.Q(primary=True),
                fields=("primary",),
                name="one_primary_laboratory",
                violation_error_code="one_primary_laboratory",
                violation_error_message="A practice has one primary laboratory.",
            ),
        ),
    ]
