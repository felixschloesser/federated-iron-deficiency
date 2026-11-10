from typing import ClassVar

import django.db.models.deletion
from django.apps.registry import Apps
from django.conf import settings
from django.db import migrations, models
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.operations.base import Operation

TARGET_CHOICES = [
    (80, "80%"),
    (85, "85%"),
    (90, "90%"),
    (95, "95%"),
    (100, "100%"),
]


def forget_deployments(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    """A deployment now records who deployed it and at which target; earlier ones
    record neither, so none is kept. Nothing is deployed outside development."""
    apps.get_model("deployment", "Deployment").objects.all().delete()


class Migration(migrations.Migration):
    dependencies: ClassVar[list[tuple[str, str]]] = [
        ("deployment", "0004_threshold_from_zero_to_one"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations: ClassVar[list[Operation]] = [
        migrations.CreateModel(
            name="TargetSensitivity",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "percent",
                    models.PositiveSmallIntegerField(choices=TARGET_CHOICES),
                ),
                ("set_at", models.DateTimeField()),
                (
                    "set_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(percent__in=[80, 85, 90, 95, 100]),
                        name="percent_offered",
                        violation_error_code="target_sensitivity_not_offered",
                        violation_error_message=(
                            "A target sensitivity is one of 80, 85, 90, 95 and 100%."
                        ),
                    )
                ],
            },
        ),
        migrations.RunPython(forget_deployments, migrations.RunPython.noop),
        # The defaults fill no row: none is left.
        migrations.AddField(
            model_name="deployment",
            name="deployed_by",
            field=models.ForeignKey(
                default=0,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="deployment",
            name="target_sensitivity",
            field=models.PositiveSmallIntegerField(choices=TARGET_CHOICES, default=0),
            preserve_default=False,
        ),
        migrations.AddConstraint(
            model_name="deployment",
            constraint=models.CheckConstraint(
                condition=models.Q(target_sensitivity__in=[80, 85, 90, 95, 100]),
                name="target_sensitivity_offered",
                violation_error_code="target_sensitivity_not_offered",
                violation_error_message=(
                    "A target sensitivity is one of 80, 85, 90, 95 and 100%."
                ),
            ),
        ),
    ]
