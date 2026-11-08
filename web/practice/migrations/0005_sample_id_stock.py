from typing import ClassVar

from django.db import migrations, models
from django.db.migrations.operations.base import Operation


class Migration(migrations.Migration):
    dependencies: ClassVar[list[tuple[str, str]]] = [
        ("practice", "0004_patient_number"),
    ]

    operations: ClassVar[list[Operation]] = [
        migrations.CreateModel(
            name="SampleId",
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
                ("value", models.CharField(max_length=20, unique=True)),
                (
                    "registered_sex",
                    models.CharField(
                        choices=[("female", "Female"), ("male", "Male")], max_length=6
                    ),
                ),
                ("age", models.PositiveSmallIntegerField()),
            ],
        ),
        migrations.RemoveField(
            model_name="patient",
            name="patient_number",
        ),
        migrations.AlterField(
            model_name="sample",
            name="sample_id",
            field=models.OneToOneField(
                on_delete=models.PROTECT, related_name="sample", to="practice.sampleid"
            ),
        ),
    ]
