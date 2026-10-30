from typing import ClassVar

from django.db import migrations, models
from django.db.migrations.operations.base import Operation


class Migration(migrations.Migration):
    dependencies: ClassVar[list[tuple[str, str]]] = [("practice", "0001_split")]

    operations: ClassVar[list[Operation]] = [
        migrations.AddField(
            model_name="labreport",
            name="ferritin_suggested",
            field=models.BooleanField(default=False),
        ),
        # The only comment the hospital ever sent was the suggestion (R9). SQL, as
        # the current model, which type checking reads, has no comment field.
        migrations.RunSQL(
            "UPDATE practice_labreport SET ferritin_suggested = TRUE"
            " WHERE comment <> ''",
            migrations.RunSQL.noop,
        ),
        migrations.RemoveField(model_name="labreport", name="comment"),
    ]
