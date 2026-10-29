from typing import Any

from django import forms

from web.practice.models import ClinicalIndication, GeneralPractitioner, Patient, Test


class OrderForm(forms.Form):
    """An order for one test; the indication field only for a test that takes one."""

    patient = forms.ModelChoiceField(queryset=Patient.objects.none())
    # The service refuses a missing indication (indication_required).
    indication = forms.TypedChoiceField(
        label="Clinical indication",
        choices=ClinicalIndication.choices,
        coerce=ClinicalIndication,
        empty_value=None,
        required=False,
        widget=forms.RadioSelect,
    )

    def __init__(
        self,
        *args: Any,
        general_practitioner: GeneralPractitioner,
        test: Test,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        patient = self.fields["patient"]
        if isinstance(patient, forms.ModelChoiceField):
            patient.queryset = general_practitioner.patients.order_by("name")
        if not test.takes_indication():
            del self.fields["indication"]
