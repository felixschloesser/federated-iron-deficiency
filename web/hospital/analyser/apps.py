from django.apps import AppConfig


class AnalyserConfig(AppConfig):
    """The laboratory's analyser (report, P9), simulated for the demo from NHANES
    participants. The laboratory knows it only through web/hospital/analyser/port.py."""

    name = "web.hospital.analyser"
    label = "analyser"
    verbose_name = "Analyser (the demo's stand-in)"
