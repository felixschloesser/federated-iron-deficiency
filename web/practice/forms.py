from typing import Any

from django import forms
from django.core.exceptions import ValidationError

from web.practice.models import INDICATION_REQUIRED, Laboratory
from web.shared.forms import NamedLabels
from web.shared.vocabulary import ClinicalIndication, Test


class OrderForm(NamedLabels, forms.Form):
    """An order for one test; asks the indication only for a test that takes one."""

    # Required only for a test that takes one; checked in clean_indication, so the
    # error has the order's own code and sits beside the field.
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
        """Only on a form that asks for an indication (a CBC's): it needs one. The
        database holds the rule too (Order's constraints)."""
        indication: ClinicalIndication | None = self.cleaned_data.get("indication")
        if indication is None:
            raise ValidationError(INDICATION_REQUIRED, code="indication_required")
        return indication


class CollectSampleForm(NamedLabels, forms.Form):
    """Which laboratory the sample goes to (features/practice/ordering.feature); left out by a practice with one,
    whose single Collect sample button posts no choice."""

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
