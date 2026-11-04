from typing import ClassVar

from django.apps.registry import Apps
from django.db import migrations, models
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.operations.base import Operation
from django.utils.text import slugify


def folder_from_name(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    """The folder each laboratory's certificates are in today: from its name."""
    laboratory = apps.get_model("practice", "Laboratory")
    for row in laboratory.objects.all():
        row.folder = slugify(row.name)
        row.save(update_fields=["folder"])


class Migration(migrations.Migration):
    dependencies: ClassVar[list[tuple[str, str]]] = [("practice", "0002_laboratories")]

    operations: ClassVar[list[Operation]] = [
        migrations.AddField(
            model_name="laboratory",
            name="folder",
            field=models.CharField(default="", max_length=100),
            preserve_default=False,
        ),
        migrations.RunPython(folder_from_name, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="laboratory",
            name="folder",
            field=models.CharField(max_length=100, unique=True),
        ),
    ]
