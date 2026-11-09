from typing import ClassVar

from django.db import migrations
from django.db.migrations.operations.base import Operation


class Migration(migrations.Migration):
    dependencies: ClassVar[list[tuple[str, str]]] = [
        ("practice", "0007_lab_report_results_named"),
    ]

    operations: ClassVar[list[Operation]] = [
        migrations.RemoveField(model_name="sampleid", name="age"),
        migrations.RemoveField(model_name="sampleid", name="registered_sex"),
    ]
