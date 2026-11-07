from typing import ClassVar

import django.db.models.deletion
from django.db import migrations, models
from django.db.migrations.operations.base import Operation


class Migration(migrations.Migration):
    dependencies: ClassVar[list[tuple[str, str]]] = [
        ("practice", "0001_initial"),
    ]

    operations: ClassVar[list[Operation]] = [
        migrations.CreateModel(
            name="Laboratory",
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
                ("name", models.CharField(max_length=100, unique=True)),
                ("address", models.CharField(max_length=200)),
            ],
        ),
        migrations.AddField(
            model_name="sample",
            name="laboratory",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="samples",
                to="practice.laboratory",
            ),
        ),
    ]
