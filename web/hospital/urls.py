"""The URLs of the hospital's web app."""

from django.urls import include, path

from web.shared.urls import *

urlpatterns = [
    *urlpatterns,
    path("lab/", include("web.hospital.lab.urls")),
    path("deployment/", include("web.hospital.deployment.urls")),
    path("cohort/", include("web.hospital.cohort.urls")),
]
