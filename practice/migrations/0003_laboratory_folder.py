from typing import ClassVar

from django.db import migrations, models
from django.db.migrations.operations.base import Operation


class Migration(migrations.Migration):
    # The certificate folder, unique, as databases applied it; 0004 removes it.
    # Filled by SQL with each row's own id, unique like the slug it once held:
    # the model has no such field any more for Python to set.
    dependencies: ClassVar[list[tuple[str, str]]] = [("practice", "0002_laboratories")]

    operations: ClassVar[list[Operation]] = [
        migrations.AddField(
            model_name="laboratory",
            name="folder",
            field=models.CharField(default="", max_length=100),
            preserve_default=False,
        ),
        migrations.RunSQL(
            "UPDATE practice_laboratory SET folder = CAST(id AS TEXT)",
            migrations.RunSQL.noop,
        ),
        migrations.AlterField(
            model_name="laboratory",
            name="folder",
            field=models.CharField(max_length=100, unique=True),
        ),
    ]
