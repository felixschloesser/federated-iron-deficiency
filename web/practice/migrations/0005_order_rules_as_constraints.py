from typing import ClassVar

from django.db import migrations, models
from django.db.migrations.operations.base import Operation


class Migration(migrations.Migration):
    dependencies: ClassVar[list[tuple[str, str]]] = [
        ("practice", "0004_guideline_indications"),
    ]

    operations: ClassVar[list[Operation]] = [
        migrations.AddConstraint(
            model_name="order",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("test__in", ["cbc"]), _negated=True),
                    ("indication__isnull", False),
                    _connector="OR",
                ),
                name="indication_required",
                violation_error_code="indication_required",
                violation_error_message="A CBC needs a clinical indication.",
            ),
        ),
        migrations.AddConstraint(
            model_name="order",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("test__in", ["cbc"]), ("indication__isnull", True), _connector="OR"
                ),
                name="indication_not_applicable",
                violation_error_code="indication_not_applicable",
                violation_error_message="Ferritin takes no clinical indication.",
            ),
        ),
        migrations.AlterConstraint(
            model_name="order",
            name="one_order_per_sample_and_test",
            constraint=models.UniqueConstraint(
                fields=("sample", "test"),
                name="one_order_per_sample_and_test",
                violation_error_code="already_ordered",
                violation_error_message="This sample already has this test.",
            ),
        ),
    ]
