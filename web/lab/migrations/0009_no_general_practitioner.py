from typing import ClassVar

from django.db import migrations
from django.db.migrations.operations.base import Operation


class Migration(migrations.Migration):
    dependencies: ClassVar[list[tuple[str, str]]] = [("lab", "0008_sample_practice")]

    # The practice, by its certificate name, says who ordered (R13, R14).
    operations: ClassVar[list[Operation]] = [
        migrations.RemoveField(model_name="laborder", name="general_practitioner"),
    ]
