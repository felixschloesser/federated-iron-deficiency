"""The hospital knows each practice by the certificate name it issued; the
practice names samples held become practices, named after their slug."""

from typing import ClassVar

from django.apps.registry import Apps
from django.db import migrations, models
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.operations.base import Operation
from django.utils.text import slugify


def practices_from_names(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    # SQL, not the historical models: their fields are not what the type checker
    # knows of today's.
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SELECT DISTINCT practice FROM lab_sample")
        for (name,) in cursor.fetchall():
            certificate_name = slugify(name)[:100] or "practice"
            cursor.execute(
                "INSERT INTO lab_practice (certificate_name, name) VALUES (%s, %s)"
                " ON CONFLICT (certificate_name) DO NOTHING",
                [certificate_name, name],
            )
            cursor.execute(
                "UPDATE lab_sample SET practice_record_id = (SELECT id FROM"
                " lab_practice WHERE certificate_name = %s) WHERE practice = %s",
                [certificate_name, name],
            )


class Migration(migrations.Migration):
    dependencies: ClassVar[list[tuple[str, str]]] = [
        ("lab", "0002_practice_no_general_practitioner")
    ]

    operations: ClassVar[list[Operation]] = [
        migrations.CreateModel(
            name="Practice",
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
                ("certificate_name", models.SlugField(max_length=100, unique=True)),
                ("name", models.CharField(max_length=100)),
            ],
        ),
        migrations.AddField(
            model_name="sample",
            name="practice_record",
            field=models.ForeignKey(
                null=True,
                on_delete=models.deletion.PROTECT,
                related_name="samples",
                to="lab.practice",
            ),
        ),
        migrations.RunPython(practices_from_names, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name="sample", name="one_sample_per_practice"
        ),
        migrations.RemoveField(model_name="sample", name="practice"),
        migrations.RenameField(
            model_name="sample", old_name="practice_record", new_name="practice"
        ),
        migrations.AlterField(
            model_name="sample",
            name="practice",
            field=models.ForeignKey(
                on_delete=models.deletion.PROTECT,
                related_name="samples",
                to="lab.practice",
            ),
        ),
        migrations.AddConstraint(
            model_name="sample",
            constraint=models.UniqueConstraint(
                fields=("practice", "sample_id"), name="one_sample_per_practice"
            ),
        ),
    ]
