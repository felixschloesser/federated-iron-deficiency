from django import forms

from web.vocabulary import RegisteredSex, Test


class LabOrderForm(forms.Form):
    """A lab order as it arrives (DF23): checked like any form before the service."""

    sample_id = forms.CharField(max_length=20)
    test = forms.TypedChoiceField(choices=Test.choices, coerce=Test)
    # Not required: a lab order without it is not for a screened indication.
    screened_indication = forms.BooleanField(required=False)
    registered_sex = forms.TypedChoiceField(
        choices=RegisteredSex.choices, coerce=RegisteredSex
    )
    age = forms.IntegerField(min_value=0)
    ordered_at = forms.DateTimeField()
