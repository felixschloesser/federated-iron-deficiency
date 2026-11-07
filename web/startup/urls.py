"""The startup's web app's pages."""

from django.urls import include, path

from web.shared.urls import *

urlpatterns = [
    *urlpatterns,
    path("training/", include("web.startup.training.urls")),
]
