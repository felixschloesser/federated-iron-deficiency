from django import forms

from web.forms import NamedLabels


class SubmitRunForm(NamedLabels, forms.Form):
    threshold = forms.FloatField(
        initial=0.5,
        help_text=(
            "The screening suggests ferritin when the model's probability of iron"
            " deficiency reaches it; between 0 and 1."
        ),
        widget=forms.NumberInput(attrs={"step": "0.01"}),
    )
