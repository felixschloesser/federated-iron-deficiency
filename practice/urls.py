"""The practice's web app's pages."""

from django.urls import include, path

from shared.urls import *

urlpatterns = [
    *urlpatterns,
    path("practice/", include("practice.pages")),
]
