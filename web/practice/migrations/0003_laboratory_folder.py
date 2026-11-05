from typing import ClassVar

from django.db import migrations, models
from django.db.migrations.operations.base import Operation


class Migration(migrations.Migration):
    # Was the certificate folder, unique and filled from the name; 0004 removes
    # it, so a database migrating now only passes through the column.
    dependencies: ClassVar[list[tuple[str, str]]] = [("practice", "0002_laboratories")]

    operations: ClassVar[list[Operation]] = [
        migrations.AddField(
            model_name="laboratory",
            name="folder",
            field=models.CharField(default="", max_length=100),
            preserve_default=False,
        ),
    ]
