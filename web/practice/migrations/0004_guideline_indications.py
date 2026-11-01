from typing import ClassVar

from django.db import migrations, models
from django.db.migrations.operations.base import Operation


class Migration(migrations.Migration):
    dependencies: ClassVar[list[tuple[str, str]]] = [("practice", "0003_samples")]

    operations: ClassVar[list[Operation]] = [
        migrations.AlterField(
            model_name="order",
            name="indication",
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
                max_length=24,
                null=True,
            ),
        ),
        # The report's example of a non-specific complaint was mild tiredness.
        migrations.RunSQL(
            "UPDATE practice_order SET indication = 'unexplained_fatigue'"
            " WHERE indication = 'non_specific_complaint'",
            migrations.RunSQL.noop,
        ),
    ]
