from typing import ClassVar

import django.db.models.deletion
from django.db import migrations, models
from django.db.migrations.operations.base import Operation


class Migration(migrations.Migration):
    dependencies: ClassVar[list[tuple[str, str]]] = [
        ("practice", "0002_lab_report_ferritin_suggested")
    ]

    operations: ClassVar[list[Operation]] = [
        migrations.RenameField(
            model_name="patient", old_name="sample_id", new_name="nhanes_number"
        ),
        migrations.CreateModel(
            name="Sample",
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
                ("sample_id", models.CharField(max_length=20, unique=True)),
                ("collected_at", models.DateTimeField()),
                (
                    "patient",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="samples",
                        to="practice.patient",
                    ),
                ),
            ],
        ),
        # The old copy of the sample ID frees the column name for the new key.
        migrations.RenameField(
            model_name="order", old_name="sample_id", new_name="old_sample_id"
        ),
        migrations.AddField(
            model_name="order",
            name="sample",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="orders",
                to="practice.sample",
            ),
        ),
        # Until now a patient had one sample, its ID on every order; it keeps that
        # ID and is collected at the first order. SQL, as the current model, which
        # type checking reads, has no old_sample_id.
        migrations.RunSQL(
            "INSERT INTO practice_sample (patient_id, sample_id, collected_at)"
            " SELECT patient_id, old_sample_id, MIN(ordered_at) FROM practice_order"
            " GROUP BY patient_id, old_sample_id",
            migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            "UPDATE practice_order SET sample_id = (SELECT id FROM practice_sample"
            " WHERE practice_sample.sample_id = practice_order.old_sample_id)",
            migrations.RunSQL.noop,
        ),
        migrations.AlterField(
            model_name="order",
            name="sample",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="orders",
                to="practice.sample",
            ),
        ),
        migrations.RemoveConstraint(model_name="order", name="one_test_per_patient"),
        migrations.RemoveField(model_name="order", name="old_sample_id"),
        migrations.RemoveField(model_name="order", name="patient"),
        migrations.AddConstraint(
            model_name="order",
            constraint=models.UniqueConstraint(
                fields=("sample", "test"), name="one_order_per_sample_and_test"
            ),
        ),
    ]
