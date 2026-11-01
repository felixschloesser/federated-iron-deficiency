from typing import ClassVar

from django.db import migrations, models
from django.db.migrations.operations.base import Operation


class Migration(migrations.Migration):
    dependencies: ClassVar[list[tuple[str, str]]] = [
        ("lab", "0005_guideline_indications"),
        ("deployment", "0002_screening_model"),
    ]

    operations: ClassVar[list[Operation]] = [
        migrations.AlterField(
            model_name="laborder",
            name="not_screened_reason",
            field=models.CharField(
                blank=True,
                choices=[
                    ("indication", "clinical indication not screened"),
                    ("sex", "registered sex not female"),
                    ("age", "age outside 18–49"),
                    ("no_deployed_model", "no screening model deployed"),
                    ("deployed_model_changed", "deployed model file changed"),
                ],
                max_length=22,
                null=True,
            ),
        ),
    ]
