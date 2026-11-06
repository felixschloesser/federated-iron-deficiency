from django.urls import path

from web.lab import views

app_name = "lab"
urlpatterns = [
    path("orders/", views.ToAnalyseView.as_view(), name="orders"),
    path("orders/analysed/", views.AnalysedView.as_view(), name="analysed"),
    path(
        "orders/<int:pk>/analyse/",
        views.RunAnalyserView.as_view(),
        name="analyse",
    ),
]
