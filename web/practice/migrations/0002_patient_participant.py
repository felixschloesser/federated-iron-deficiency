from typing import ClassVar

import django.db.models.deletion
from django.apps.registry import Apps
from django.db import migrations, models
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.operations.base import Operation


def remove_patients_without_participant(
    apps: Apps, schema_editor: BaseDatabaseSchemaEditor
) -> None:
    """Demo patients from before NHANES participants existed; seed_demo recreates them."""
    apps.get_model("practice", "Order").objects.all().delete()
    apps.get_model("practice", "Patient").objects.all().delete()


class Migration(migrations.Migration):
    dependencies: ClassVar[list[tuple[str, str]]] = [
        ("nhanes", "0001_initial"),
        ("practice", "0001_initial"),
    ]

    operations: ClassVar[list[Operation]] = [
        migrations.RunPython(
            remove_patients_without_participant, migrations.RunPython.noop
        ),
        migrations.AddField(
            model_name="patient",
            name="participant",
            # The default fills no row: the patients were removed above.
            field=models.OneToOneField(
                default=0,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="patient",
                to="nhanes.participant",
            ),
            preserve_default=False,
        ),
    ]
