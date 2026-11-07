from typing import ClassVar

from django.db import migrations
from django.db.migrations.operations.base import Operation


class Migration(migrations.Migration):
    dependencies: ClassVar[list[tuple[str, str]]] = [
        ("practice", "0003_laboratory_folder")
    ]

    operations: ClassVar[list[Operation]] = [
        migrations.RemoveField(model_name="laboratory", name="folder"),
    ]
