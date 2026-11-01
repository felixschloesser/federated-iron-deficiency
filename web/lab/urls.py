from django.urls import path

from web.lab import views

app_name = "lab"
urlpatterns = [
    path("lab-orders/", views.ToAnalyseView.as_view(), name="to_analyse"),
    path("lab-orders/analysed/", views.AnalysedView.as_view(), name="analysed"),
    path(
        "lab-orders/<int:pk>/analyse/",
        views.RunAnalyserView.as_view(),
        name="run_analyser",
    ),
]
