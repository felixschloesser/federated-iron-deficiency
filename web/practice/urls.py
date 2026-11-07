"""The practice's web app's pages."""

from django.urls import include, path

from web.shared.urls import *

urlpatterns = [
    *urlpatterns,
    path("practice/", include("web.practice.pages")),
]
