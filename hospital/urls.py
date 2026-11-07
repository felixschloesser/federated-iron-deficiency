"""The hospital's web app's pages."""

from django.urls import include, path

from shared.urls import *

urlpatterns = [
    *urlpatterns,
    path("lab/", include("hospital.lab.urls")),
    path("deployment/", include("hospital.deployment.urls")),
    path("cohort/", include("hospital.cohort.urls")),
]
