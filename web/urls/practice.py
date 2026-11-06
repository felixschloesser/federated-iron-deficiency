"""The practice's web app's pages."""

from django.urls import include, path

from web.urls.base import *

urlpatterns = [
    *urlpatterns,
    path("practice/", include("web.practice.urls")),
]
