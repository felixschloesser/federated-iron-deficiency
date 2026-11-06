"""The hospital's web app's pages."""

from django.urls import include, path

from web.urls.base import *

urlpatterns = [
    *urlpatterns,
    path("lab/", include("web.hospital.lab.urls")),
    path("deployment/", include("web.hospital.deployment.urls")),
    path("cohort/", include("web.hospital.cohort.urls")),
]
