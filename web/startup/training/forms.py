import tomllib
from typing import Any

from django import forms
from django.conf import settings


class SubmitRunForm(forms.Form):
    """A training run's configuration: the parameters the data scientist may
    choose, within bounds. Each field is named after its run configuration key
    (`num_server_rounds` for `num-server-rounds`). Left out on purpose: the
    fraction of hospitals evaluating (fewer than all would make the AUROC across
    hospitals one hospital's), the folder final models are kept in, and the W&B
    key."""

    num_server_rounds = forms.IntegerField(label="Rounds", min_value=1, max_value=20)
    local_epochs = forms.IntegerField(label="Local epochs", min_value=1, max_value=10)
    learning_rate = forms.FloatField(
        label="Learning rate", min_value=0.0001, max_value=1.0
    )
    weight_decay = forms.FloatField(label="Weight decay", min_value=0.0, max_value=0.1)
    # At least 32, because a batch of one record would make each gradient a
    # single patient's.
    batch_size = forms.IntegerField(label="Batch size", min_value=32, max_value=1024)
    model_seed = forms.IntegerField(label="Seed", min_value=0, max_value=2**32 - 1)

    @classmethod
    def defaults(cls) -> dict[str, Any]:
        """The app's default run configuration from pyproject.toml, by field name."""
        with (settings.BASE_DIR / "pyproject.toml").open("rb") as file:
            config = tomllib.load(file)["tool"]["flwr"]["app"]["config"]
        return {name: config[name.replace("_", "-")] for name in cls.base_fields}

    def run_configuration(self) -> dict[str, int | float]:
        """The cleaned values under their run configuration keys."""
        return {
            name.replace("_", "-"): value for name, value in self.cleaned_data.items()
        }
