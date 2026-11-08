from typing import ClassVar

from django.db import migrations, models
from django.db.migrations.operations.base import Operation


class Migration(migrations.Migration):
    dependencies: ClassVar[list[tuple[str, str]]] = [
        ("lab", "0004_not_screened_labels"),
    ]

    operations: ClassVar[list[Operation]] = [
        migrations.AlterField(
            model_name="testrequest",
            name="not_screened_reason",
            field=models.CharField(
                blank=True,
                choices=[
                    ("not_eligible", "Not eligible"),
                    ("no_deployed_model", "No screening model is deployed"),
                    (
                        "deployed_model_changed",
                        "The deployed screening model changed on disk since it was deployed",
                    ),
                ],
                max_length=22,
                null=True,
            ),
        ),
    ]
