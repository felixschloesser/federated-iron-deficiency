"""A lab order says only whether its indication is screened (R4, R25), and a CBC
outside the screening is not eligible, never why (R5)."""

from typing import ClassVar

from django.apps.registry import Apps
from django.db import migrations, models
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.operations.base import Operation

# The screened indications and the patient reasons as they stood when this
# migration was written; a migration keeps its own history.
SCREENED = ("suspected_anaemia", "suspected_ibs", "unexplained_fatigue")
PATIENT_REASONS = ("indication", "sex", "age")


def forget_the_indication(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    lab_order = apps.get_model("lab", "LabOrder")
    # The historical model still has `indication`; today's, which type checkers
    # read, has not: the lookup is spelled out as data.
    screened = {"indication__in": SCREENED}
    lab_order.objects.filter(**screened).update(screened_indication=True)
    lab_order.objects.filter(not_screened_reason__in=PATIENT_REASONS).update(
        not_screened_reason="not_eligible"
    )


class Migration(migrations.Migration):
    dependencies: ClassVar[list[tuple[str, str]]] = [
        ("lab", "0006_screening_model_wording"),
    ]

    operations: ClassVar[list[Operation]] = [
        migrations.AddField(
            model_name="laborder",
            name="screened_indication",
            field=models.BooleanField(default=False),
        ),
        # Kept from the indication before it goes; no way back to which it was.
        migrations.RunPython(forget_the_indication, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="laborder",
            name="indication",
        ),
        migrations.AlterField(
            model_name="laborder",
            name="not_screened_reason",
            field=models.CharField(
                blank=True,
                choices=[
                    ("not_eligible", "not eligible"),
                    ("no_deployed_model", "no screening model deployed"),
                    ("deployed_model_changed", "deployed model file changed"),
                ],
                max_length=22,
                null=True,
            ),
        ),
    ]
