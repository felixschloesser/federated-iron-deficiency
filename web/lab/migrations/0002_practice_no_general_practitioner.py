from typing import ClassVar

from django.db import migrations, models
from django.db.migrations.operations.base import Operation


class Migration(migrations.Migration):
    dependencies: ClassVar[list[tuple[str, str]]] = [("lab", "0001_initial")]

    operations: ClassVar[list[Operation]] = [
        # The report's word, not the developer's: a sample's practice, by its
        # certificate name. A rename, so every sample keeps its value.
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
        # The practice says who ordered (features/access.feature): no general practitioner's name.
        migrations.RemoveField(model_name="laborder", name="general_practitioner"),
    ]
