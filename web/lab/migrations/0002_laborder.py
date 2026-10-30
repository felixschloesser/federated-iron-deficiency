from typing import ClassVar

import django.db.models.deletion
from django.apps.registry import Apps
from django.db import migrations, models
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.operations.base import Operation


def remove_demo_samples(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    """Demo samples from before lab orders; they pointed at practice orders."""
    apps.get_model("lab", "Sample").objects.all().delete()


class Migration(migrations.Migration):
    dependencies: ClassVar[list[tuple[str, str]]] = [("lab", "0001_initial")]

    operations: ClassVar[list[Operation]] = [
        migrations.RunPython(remove_demo_samples, migrations.RunPython.noop),
        migrations.RemoveField(model_name="sample", name="order"),
        migrations.RemoveField(model_name="sample", name="analysed_at"),
        migrations.RemoveField(model_name="sample", name="results"),
        migrations.AlterField(
            model_name="sample",
            name="received_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name="LabOrder",
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
                (
                    "test",
                    models.CharField(
                        choices=[("cbc", "CBC"), ("ferritin", "ferritin")], max_length=8
                    ),
                ),
                (
                    "indication",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("non_specific_complaint", "Non-specific complaint"),
                            ("other", "Other"),
                        ],
                        max_length=22,
                        null=True,
                    ),
                ),
                (
                    "registered_sex",
                    models.CharField(
                        choices=[("female", "Female"), ("male", "Male")], max_length=6
                    ),
                ),
                ("age", models.PositiveSmallIntegerField()),
                ("general_practitioner", models.CharField(max_length=100)),
                ("ordered_at", models.DateTimeField()),
                ("analysed_at", models.DateTimeField(blank=True, null=True)),
                ("results", models.JSONField(blank=True, null=True)),
                (
                    "sample",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="lab_orders",
                        to="lab.sample",
                    ),
                ),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(
                        fields=("sample", "test"), name="one_test_per_sample"
                    )
                ],
            },
        ),
    ]
