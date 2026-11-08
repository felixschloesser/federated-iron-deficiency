from typing import ClassVar

from django.db import migrations, models
from django.db.migrations.operations.base import Operation


class Migration(migrations.Migration):
    dependencies: ClassVar[list[tuple[str, str]]] = [
        ("lab", "0002_name_and_slug"),
    ]

    operations: ClassVar[list[Operation]] = [
        migrations.RemoveField(
            model_name="testrequest",
            name="screened_indication",
        ),
        migrations.AddField(
            model_name="testrequest",
            name="clinical_indication",
            field=models.CharField(
                blank=True,
                choices=[
                    ("suspected_anaemia", "Suspected anaemia"),
                    ("suspected_ibs", "Suspected irritable bowel syndrome"),
                    ("unexplained_fatigue", "Unexplained fatigue"),
                    ("start_of_pregnancy", "Start of pregnancy"),
                    ("ckd_follow_up", "Chronic kidney disease follow-up"),
                    ("other", "Other"),
                ],
                max_length=19,
                null=True,
            ),
        ),
    ]
