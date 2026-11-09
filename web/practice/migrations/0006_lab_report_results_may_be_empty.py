from typing import ClassVar

from django.db import migrations, models
from django.db.migrations.operations.base import Operation


class Migration(migrations.Migration):
    dependencies: ClassVar[list[tuple[str, str]]] = [
        ("practice", "0005_sample_id_stock"),
    ]

    operations: ClassVar[list[Operation]] = [
        migrations.AlterField(
            model_name="labreport",
            name="results",
            field=models.JSONField(blank=True),
        ),
    ]
