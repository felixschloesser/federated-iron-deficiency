from typing import ClassVar

from django.db import migrations, models
from django.db.migrations.operations.base import Operation


class Migration(migrations.Migration):
    initial = True

    dependencies: ClassVar[list[tuple[str, str]]] = []

    operations: ClassVar[list[Operation]] = [
        migrations.CreateModel(
            name="Participant",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("seqn", models.PositiveIntegerField(unique=True)),
                ("cbc", models.JSONField()),
                ("ferritin", models.FloatField(blank=True, null=True)),
            ],
        ),
    ]
