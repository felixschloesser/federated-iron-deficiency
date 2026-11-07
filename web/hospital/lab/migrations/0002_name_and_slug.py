from typing import ClassVar

from django.db import migrations, models
from django.db.migrations.operations.base import Operation


class Migration(migrations.Migration):
    dependencies: ClassVar[list[tuple[str, str]]] = [
        ("lab", "0001_initial"),
    ]

    operations: ClassVar[list[Operation]] = [
        migrations.RemoveField(
            model_name="practice",
            name="certificate_name",
        ),
        migrations.AddField(
            model_name="practice",
            name="slug",
            field=models.SlugField(default="", editable=False, max_length=100),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="practice",
            name="name",
            field=models.CharField(max_length=100, unique=True),
        ),
        migrations.AddConstraint(
            model_name="practice",
            constraint=models.UniqueConstraint(
                fields=("slug",),
                name="one_practice_per_slug",
                violation_error_code="slug_taken",
                violation_error_message="Another practice's name has this slug.",
            ),
        ),
    ]
