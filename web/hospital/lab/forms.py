from django import forms

from web.shared.vocabulary import ClinicalIndication, RegisteredSex, Test


class LabOrderForm(forms.Form):
    """A lab order as it arrives (DF23): checked like any form before the service."""

    sample_id = forms.CharField(max_length=20)
    test = forms.TypedChoiceField(choices=Test.choices, coerce=Test)
    # Not required: ferritin takes none, and a CBC without one is not screened.
    clinical_indication = forms.TypedChoiceField(
        choices=ClinicalIndication.choices,
        coerce=ClinicalIndication,
        required=False,
        empty_value=None,
    )
    registered_sex = forms.TypedChoiceField(
        choices=RegisteredSex.choices, coerce=RegisteredSex
    )
    age = forms.IntegerField(min_value=0)
    ordered_at = forms.DateTimeField()
