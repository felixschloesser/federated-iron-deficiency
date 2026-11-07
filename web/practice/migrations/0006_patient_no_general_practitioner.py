from typing import ClassVar

from django.db import migrations
from django.db.migrations.operations.base import Operation


class Migration(migrations.Migration):
    """A practice has one general practitioner, so a patient needs no link to them."""

    dependencies: ClassVar[list[tuple[str, str]]] = [
        ("practice", "0005_laboratory_primary")
    ]

    operations: ClassVar[list[Operation]] = [
        migrations.RemoveField(model_name="patient", name="general_practitioner"),
    ]
