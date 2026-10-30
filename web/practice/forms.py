from typing import Any

from django import forms

from web.vocabulary import ClinicalIndication, Test


class OrderForm(forms.Form):
    """An order for one test; asks the indication only for a test that takes one."""

    # The service refuses a missing indication (indication_required).
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
