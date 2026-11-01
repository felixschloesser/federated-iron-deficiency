from django import forms

from web.vocabulary import ClinicalIndication, RegisteredSex, Test


class LabOrderForm(forms.Form):
    """A lab order as it arrives (DF23): checked like any form before the service."""

    sample_id = forms.CharField(max_length=20)
    test = forms.TypedChoiceField(choices=Test.choices, coerce=Test)
    indication = forms.TypedChoiceField(
        choices=ClinicalIndication.choices,
        coerce=ClinicalIndication,
        empty_value=None,
        required=False,
    )
    registered_sex = forms.TypedChoiceField(
        choices=RegisteredSex.choices, coerce=RegisteredSex
    )
    age = forms.IntegerField(min_value=0)
    general_practitioner = forms.CharField(max_length=100)
    ordered_at = forms.DateTimeField()
