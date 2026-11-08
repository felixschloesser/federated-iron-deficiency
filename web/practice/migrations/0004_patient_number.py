from typing import ClassVar

from django.db import migrations
from django.db.migrations.operations.base import Operation


class Migration(migrations.Migration):
    dependencies: ClassVar[list[tuple[str, str]]] = [
        ("practice", "0003_sample_laboratory_required"),
    ]

    operations: ClassVar[list[Operation]] = [
        migrations.RenameField(
            model_name="patient",
            old_name="nhanes_number",
            new_name="patient_number",
        ),
    ]
