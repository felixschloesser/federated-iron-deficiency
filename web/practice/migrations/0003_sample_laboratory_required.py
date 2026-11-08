from typing import ClassVar

from django.db import migrations, models
from django.db.migrations.operations.base import Operation


class Migration(migrations.Migration):
    dependencies: ClassVar[list[tuple[str, str]]] = [
        ("practice", "0002_rejection"),
    ]

    operations: ClassVar[list[Operation]] = [
        migrations.AlterField(
            model_name="sample",
            name="laboratory",
            field=models.ForeignKey(
                on_delete=models.PROTECT,
                related_name="samples",
                to="practice.laboratory",
            ),
        ),
    ]
