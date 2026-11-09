from django.apps import AppConfig


class AnalyserConfig(AppConfig):
    """The laboratory's analyser, simulated for the demo from NHANES participants.
    The laboratory reaches it only through web/hospital/analyser/port.py."""

    name = "web.hospital.analyser"
    label = "analyser"
    verbose_name = "Analyser (the demo's stand-in)"
