from typing import ClassVar

from django.db import migrations
from django.db.migrations.operations.base import Operation


class Migration(migrations.Migration):
    dependencies: ClassVar[list[tuple[str, str]]] = [
        ("lab", "0006_four_screening_results"),
    ]

    operations: ClassVar[list[Operation]] = [
        migrations.RenameField(
            model_name="testrequest",
            old_name="ordered_at",
            new_name="collected_at",
        ),
    ]
