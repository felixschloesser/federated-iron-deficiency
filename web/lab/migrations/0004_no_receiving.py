from typing import ClassVar

from django.db import migrations
from django.db.migrations.operations.base import Operation


class Migration(migrations.Migration):
    dependencies: ClassVar[list[tuple[str, str]]] = [("lab", "0003_screening")]

    operations: ClassVar[list[Operation]] = [
        migrations.RemoveField(model_name="sample", name="received_at"),
    ]
