from typing import ClassVar

from django.db import migrations
from django.db.migrations.operations.base import Operation


class Migration(migrations.Migration):
    dependencies: ClassVar[list[tuple[str, str]]] = [
        ("deployment", "0002_required_stored_at_and_federated_auroc"),
        ("lab", "0004_not_screened_labels"),
    ]

    operations: ClassVar[list[Operation]] = [
        migrations.RenameModel(
            old_name="ScreeningModel", new_name="DeployedScreeningModel"
        ),
        migrations.RenameField(
            model_name="deployment",
            old_name="screening_model",
            new_name="deployed_screening_model",
        ),
    ]
