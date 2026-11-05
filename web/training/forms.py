from django import forms


class SubmitRunForm(forms.Form):
    """Submitting a training run takes no input: the form carries its errors."""
