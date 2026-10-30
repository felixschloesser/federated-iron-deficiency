from typing import ClassVar

from django.db import migrations, models
from django.db.migrations.operations.base import Operation


class Migration(migrations.Migration):
    dependencies: ClassVar[list[tuple[str, str]]] = [("lab", "0001_split")]

    operations: ClassVar[list[Operation]] = [
        # Samples from before have no known app: an empty name, which no
        # client certificate carries, so their lab reports are never handed out.
        migrations.AddField(
            model_name="sample",
            name="client",
            field=models.CharField(default="", max_length=100),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="sample",
            name="sample_id",
            field=models.CharField(max_length=20),
        ),
        migrations.AddConstraint(
            model_name="sample",
            constraint=models.UniqueConstraint(
                fields=("client", "sample_id"), name="one_sample_per_client"
            ),
        ),
    ]
