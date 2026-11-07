from typing import ClassVar

import django.db.models.deletion
from django.db import migrations, models
from django.db.migrations.operations.base import Operation


class Migration(migrations.Migration):
    """The laboratory's word for what it analyses: a test request (WHO LQMS),
    not the lab order (DF23) it arrived as. Rows and their order kept."""

    dependencies: ClassVar[list[tuple[str, str]]] = [
        ("lab", "0004_role_on_user"),
        ("deployment", "0004_role_on_user"),
    ]

    operations: ClassVar[list[Operation]] = [
        migrations.RenameModel(old_name="LabOrder", new_name="TestRequest"),
        migrations.AlterField(
            model_name="testrequest",
            name="sample",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="test_requests",
                to="lab.sample",
            ),
        ),
    ]
