from typing import ClassVar

from django.db import migrations, models
from django.db.migrations.operations.base import Operation


class Migration(migrations.Migration):
    dependencies: ClassVar[list[tuple[str, str]]] = [
        ("lab", "0005_deployed_screening_model_labels"),
    ]

    operations: ClassVar[list[Operation]] = [
        migrations.RemoveField(
            model_name="testrequest",
            name="not_screened_reason",
        ),
        migrations.AlterField(
            model_name="testrequest",
            name="screening_result",
            field=models.CharField(
                blank=True,
                choices=[
                    ("ferritin_suggested", "Ferritin suggested"),
                    ("ferritin_not_suggested", "Ferritin not suggested"),
                    ("not_screened", "Not screened"),
                    ("screening_failed", "Screening failed"),
                ],
                max_length=22,
                null=True,
            ),
        ),
    ]
