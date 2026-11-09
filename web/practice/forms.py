from typing import Any

from django import forms
from django.core.exceptions import ValidationError

from web.practice.models import INDICATION_REQUIRED, Laboratory
from web.shared.forms import NamedLabels
from web.shared.vocabulary import ClinicalIndication, Test


class OrderForm(NamedLabels, forms.Form):
    """An order for one test. It asks for a clinical indication only when the test
    takes one."""

    # Not required here: clean_indication requires it instead, so the error has
    # the order's own code and appears beside the field. __init__ removes the
    # field for a test that takes no indication.
    indication = forms.TypedChoiceField(
        label="Clinical indication",
        choices=ClinicalIndication.choices,
        coerce=ClinicalIndication,
        empty_value=None,
        required=False,
        widget=forms.RadioSelect,
    )

    def __init__(self, *args: Any, test: Test, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if not test.takes_indication():
            del self.fields["indication"]

    def clean_indication(self) -> ClinicalIndication:
        """Require an indication. This runs only when the form shows the field
        (for a CBC); Order's constraints enforce the same rule in the database."""
        indication: ClinicalIndication | None = self.cleaned_data.get("indication")
        if indication is None:
            raise ValidationError(INDICATION_REQUIRED, code="indication_required")
        return indication


class CollectSampleForm(NamedLabels, forms.Form):
    """The laboratory the sample goes to. A practice with one laboratory shows no
    choice: its single Collect sample button posts none, and that laboratory is
    used."""

    def clean_laboratory(self) -> Laboratory:
        laboratory: Laboratory | None = self.cleaned_data.get("laboratory")
        if laboratory is None and Laboratory.objects.count() == 1:
            laboratory = Laboratory.objects.get()
        if laboratory is None:
            raise forms.ValidationError(
                "Choose the laboratory the sample goes to.", code="laboratory_required"
            )
        return laboratory

    laboratory = forms.ModelChoiceField(
        label="Laboratory",
        queryset=Laboratory.objects.order_by("name"),
        required=False,
        empty_label=None,
        widget=forms.RadioSelect,
    )
