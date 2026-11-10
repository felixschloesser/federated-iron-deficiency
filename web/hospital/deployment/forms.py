from django import forms

from web.hospital.deployment.models import TargetPercent
from web.shared.forms import NamedLabels


class TargetSensitivityForm(NamedLabels, forms.Form):
    """The target sensitivity a laboratory director sets."""

    percent = forms.TypedChoiceField(
        label="Target sensitivity",
        choices=TargetPercent.choices,
        coerce=int,
        widget=forms.RadioSelect,
        error_messages={
            "required": "Choose a target sensitivity.",
            "invalid_choice": "Choose a target sensitivity.",
        },
    )
