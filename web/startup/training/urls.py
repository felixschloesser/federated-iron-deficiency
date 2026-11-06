from django.urls import path

from web.startup.training import views

app_name = "training"
urlpatterns = [
    path("runs/", views.TrainingRunsView.as_view(), name="runs"),
    path("runs/<int:run_id>/stop/", views.StopRunView.as_view(), name="stop"),
    path("models/", views.FinalModelsView.as_view(), name="models"),
    # slug: a run ID never holds a path separator (the file is <run_id>.pt).
    path(
        "models/<slug:run_id>/transmit/",
        views.TransmitView.as_view(),
        name="transmit",
    ),
    path(
        "models/<slug:run_id>/for-sale/",
        views.ForSaleView.as_view(),
        name="for_sale",
    ),
]
