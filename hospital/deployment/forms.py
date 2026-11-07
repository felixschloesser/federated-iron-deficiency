from django import forms


class DeployForm(forms.Form):
    """The threshold a laboratory director deploys a screening model at."""

    threshold = forms.FloatField(
        error_messages={
            "required": "Choose a threshold to deploy at.",
            "invalid": "Choose a threshold to deploy at.",
        }
    )
