from typing import ClassVar

from django.apps.registry import Apps
from django.db import migrations, models
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.operations.base import Operation


def forget_unmeasured(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    """Participants NHANES measured no ferritin for are no longer in the pool."""
    apps.get_model("analyser", "Participant").objects.filter(
        ferritin__isnull=True
    ).delete()


class Migration(migrations.Migration):
    dependencies: ClassVar[list[tuple[str, str]]] = [("analyser", "0001_initial")]

    operations: ClassVar[list[Operation]] = [
        migrations.RunPython(forget_unmeasured, migrations.RunPython.noop),
        migrations.RemoveField(model_name="participant", name="made_up_ferritin"),
        migrations.AlterField(
            model_name="participant", name="ferritin", field=models.FloatField()
        ),
    ]
