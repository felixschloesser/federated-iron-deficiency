from typing import ClassVar

from django.db import migrations, models
from django.db.migrations.operations.base import Operation


class Migration(migrations.Migration):
    """Each party's role records move into this field, then the constraints follow."""

    dependencies: ClassVar[list[tuple[str, str]]] = [("accounts", "0001_initial")]

    operations: ClassVar[list[Operation]] = [
        migrations.AddField(
            model_name="user",
            name="role",
            field=models.CharField(
                blank=True,
                choices=[
                    ("general_practitioner", "general practitioner"),
                    ("laboratory_staff", "laboratory staff"),
                    ("laboratory_director", "laboratory director"),
                    ("data_scientist", "data scientist"),
                ],
                max_length=20,
                null=True,
            ),
        ),
    ]
