from typing import ClassVar

from django.db import migrations, models
from django.db.migrations.operations.base import Operation


class Migration(migrations.Migration):
    dependencies: ClassVar[list[tuple[str, str]]] = [
        ("lab", "0007_screened_indication"),
    ]

    # The developer's word gives way to the report's: a sample's practice, by its
    # certificate name. A rename, so every sample keeps its value.
    operations: ClassVar[list[Operation]] = [
        migrations.RemoveConstraint(model_name="sample", name="one_sample_per_client"),
        migrations.RenameField(
            model_name="sample", old_name="client", new_name="practice"
        ),
        migrations.AddConstraint(
            model_name="sample",
            constraint=models.UniqueConstraint(
                fields=("practice", "sample_id"), name="one_sample_per_practice"
            ),
        ),
    ]
