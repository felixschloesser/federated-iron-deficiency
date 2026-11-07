from typing import ClassVar

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.db.migrations.operations.base import Operation


class Migration(migrations.Migration):
    """Final models are released and fetched, not transmitted: the transmissions
    go (demo history only), and releases, recipients and fetches come."""

    dependencies: ClassVar[list[tuple[str, str]]] = [
        ("training", "0003_transmission"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations: ClassVar[list[Operation]] = [
        migrations.CreateModel(
            name="Recipient",
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
        migrations.CreateModel(
            name="Release",
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
                ("final_model_run_id", models.CharField(max_length=64, unique=True)),
                ("released_at", models.DateTimeField()),
                (
                    "released_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="Fetch",
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
                ("fetched_at", models.DateTimeField()),
                (
                    "recipient",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="fetches",
                        to="training.recipient",
                    ),
                ),
                (
                    "release",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="fetches",
                        to="training.release",
                    ),
                ),
            ],
        ),
        migrations.DeleteModel(
            name="Transmission",
        ),
        migrations.AddConstraint(
            model_name="fetch",
            constraint=models.UniqueConstraint(
                fields=("release", "recipient"), name="one_fetch_per_recipient"
            ),
        ),
    ]
