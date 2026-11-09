from typing import ClassVar

from django.db import migrations, models
from django.db.migrations.operations.base import Operation

import web.practice.models


class Migration(migrations.Migration):
    dependencies: ClassVar[list[tuple[str, str]]] = [
        ("practice", "0006_lab_report_results_may_be_empty"),
    ]

    operations: ClassVar[list[Operation]] = [
        migrations.AlterField(
            model_name="labreport",
            name="results",
            field=models.JSONField(
                blank=True, validators=[web.practice.models.results_named]
            ),
        ),
    ]
