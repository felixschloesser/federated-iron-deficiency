"""The startup's data scientist, who follows its training runs."""

from django.conf import settings
from django.db import models


class DataScientist(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="data_scientist",
    )
    name = models.CharField(max_length=100)

    def __str__(self) -> str:
        return self.name
