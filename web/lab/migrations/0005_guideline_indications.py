from typing import ClassVar

from django.db import migrations, models
from django.db.migrations.operations.base import Operation


class Migration(migrations.Migration):
    dependencies: ClassVar[list[tuple[str, str]]] = [("lab", "0004_no_receiving")]

    operations: ClassVar[list[Operation]] = [
        migrations.AlterField(
            model_name="laborder",
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
        migrations.AlterField(
            model_name="laborder",
            name="not_screened_reason",
            field=models.CharField(
                blank=True,
                choices=[
                    ("indication", "clinical indication not screened"),
                    ("sex", "registered sex not female"),
                    ("age", "age outside 18–49"),
                    ("no_deployed_model", "no model deployed"),
                    ("deployed_model_changed", "deployed model file changed"),
                ],
                max_length=22,
                null=True,
            ),
        ),
        # The report's example of a non-specific complaint was mild tiredness.
        migrations.RunSQL(
            "UPDATE lab_laborder SET indication = 'unexplained_fatigue'"
            " WHERE indication = 'non_specific_complaint'",
            migrations.RunSQL.noop,
        ),
    ]
