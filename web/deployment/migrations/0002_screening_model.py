from typing import ClassVar

from django.db import migrations
from django.db.migrations.operations.base import Operation


class Migration(migrations.Migration):
    dependencies: ClassVar[list[tuple[str, str]]] = [
        ("deployment", "0001_initial"),
        # The lab's screening results point at the model, so they rename with it.
        ("lab", "0005_guideline_indications"),
    ]

    operations: ClassVar[list[Operation]] = [
        migrations.RenameModel(old_name="FinalModel", new_name="ScreeningModel"),
        migrations.RenameField(
            model_name="deployment", old_name="final_model", new_name="screening_model"
        ),
    ]
