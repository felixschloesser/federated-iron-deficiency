from django.urls import path

from web.lab import views

app_name = "lab"
urlpatterns = [
    path("samples/", views.SamplesView.as_view(), name="samples"),
    path("samples/<int:pk>/receive/", views.ReceiveView.as_view(), name="receive"),
    path(
        "lab-orders/<int:pk>/analyse/",
        views.RunAnalyserView.as_view(),
        name="run_analyser",
    ),
]
