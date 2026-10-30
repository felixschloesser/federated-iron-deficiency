from typing import ClassVar

import django.db.models.deletion
from django.db import migrations, models
from django.db.migrations.operations.base import Operation


class Migration(migrations.Migration):
    dependencies: ClassVar[list[tuple[str, str]]] = [
        ("deployment", "0001_initial"),
        ("lab", "0002_sample_client"),
    ]

    operations: ClassVar[list[Operation]] = [
        migrations.AddField(
            model_name="laborder",
            name="screening_result",
            field=models.CharField(
                blank=True,
                choices=[
                    ("ferritin_suggested", "Ferritin suggested"),
                    ("ferritin_not_suggested", "Ferritin not suggested"),
                    ("not_screened", "Not screened"),
                ],
                max_length=22,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="laborder",
            name="not_screened_reason",
            field=models.CharField(
                blank=True,
                choices=[
                    ("indication", "not a non-specific complaint"),
                    ("sex", "registered sex not female"),
                    ("age", "age outside 18–49"),
                    ("no_deployed_model", "no model deployed"),
                    ("deployed_model_changed", "deployed model file changed"),
                ],
                max_length=22,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="laborder",
            name="screened_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="screening_results",
                to="deployment.finalmodel",
            ),
        ),
    ]
