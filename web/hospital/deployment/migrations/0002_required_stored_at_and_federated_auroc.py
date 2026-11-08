from typing import ClassVar

from django.db import migrations, models
from django.db.migrations.operations.base import Operation


class Migration(migrations.Migration):
    dependencies: ClassVar[list[tuple[str, str]]] = [
        ("deployment", "0001_initial"),
    ]

    operations: ClassVar[list[Operation]] = [
        migrations.AlterField(
            model_name="screeningmodel",
            name="stored_at",
            field=models.DateTimeField(),
        ),
        migrations.AlterField(
            model_name="screeningmodel",
            name="federated_auroc",
            field=models.FloatField(),
        ),
    ]
