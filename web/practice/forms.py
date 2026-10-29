from typing import Any

from django import forms

from web.practice.models import GP, ClinicalIndication, Patient, Test


class OrderForm(forms.Form):
    patient = forms.ModelChoiceField(queryset=Patient.objects.none())
    test = forms.TypedChoiceField(choices=Test.choices, coerce=Test)
    indication = forms.TypedChoiceField(
        label="Clinical indication",
        choices=[("", "None (ferritin)"), *ClinicalIndication.choices],
        coerce=ClinicalIndication,
        empty_value=None,
        required=False,
        help_text="Required for a CBC; ferritin takes none.",
    )

    def __init__(self, *args: Any, gp: GP, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        patient = self.fields["patient"]
        if isinstance(patient, forms.ModelChoiceField):
            patient.queryset = gp.patients.order_by("name")
