from django.urls import path

from web.hospital.lab import views

app_name = "lab"
urlpatterns = [
    path("test-requests/", views.ToAnalyseView.as_view(), name="test_requests"),
    path("test-requests/analysed/", views.AnalysedView.as_view(), name="analysed"),
    path(
        "test-requests/<int:pk>/analyse/",
        views.RunAnalyserView.as_view(),
        name="analyse",
    ),
]
