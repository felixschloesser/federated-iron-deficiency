from typing import ClassVar

from django.apps.registry import Apps
from django.db import migrations, models
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.operations.base import Operation


def remove_demo_orders_and_patients(
    apps: Apps, schema_editor: BaseDatabaseSchemaEditor
) -> None:
    """Demo rows from before sample IDs; seed_demo recreates them."""
    apps.get_model("practice", "Order").objects.all().delete()
    apps.get_model("practice", "Patient").objects.all().delete()


class Migration(migrations.Migration):
    dependencies: ClassVar[list[tuple[str, str]]] = [
        ("practice", "0002_patient_participant"),
    ]

    operations: ClassVar[list[Operation]] = [
        migrations.RunPython(
            remove_demo_orders_and_patients, migrations.RunPython.noop
        ),
        migrations.RemoveField(model_name="patient", name="participant"),
        migrations.AddField(
            model_name="patient",
            name="sample_id",
            # The default fills no row: the patients were removed above.
            field=models.CharField(default="", max_length=20, unique=True),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="order",
            name="sample_id",
            field=models.CharField(default="", max_length=20),
            preserve_default=False,
        ),
        migrations.AddConstraint(
            model_name="order",
            constraint=models.UniqueConstraint(
                fields=("patient", "test"), name="one_test_per_patient"
            ),
        ),
    ]
