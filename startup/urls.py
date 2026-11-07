"""The startup's web app's pages."""

from django.urls import include, path

from shared.urls import *

urlpatterns = [
    *urlpatterns,
    path("training/", include("startup.training.urls")),
]
