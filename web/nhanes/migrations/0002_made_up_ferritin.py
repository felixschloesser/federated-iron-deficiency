from typing import ClassVar

from django.db import migrations, models
from django.db.migrations.operations.base import Operation


class Migration(migrations.Migration):
    dependencies: ClassVar[list[tuple[str, str]]] = [("nhanes", "0001_initial")]

    operations: ClassVar[list[Operation]] = [
        migrations.AddField(
            model_name="participant",
            name="made_up_ferritin",
            field=models.FloatField(blank=True, null=True),
        ),
    ]
