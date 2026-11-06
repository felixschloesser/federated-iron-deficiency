"""The startup's web app's pages."""

from django.urls import include, path

from web.urls.base import *

urlpatterns = [
    *urlpatterns,
    path("training/", include("web.startup.training.urls")),
]
