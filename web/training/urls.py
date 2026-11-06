from django.urls import path

from web.training import views

app_name = "training"
urlpatterns = [
    path("runs/", views.TrainingRunsView.as_view(), name="runs"),
    # slug: a run ID never holds a path separator (the file is <run_id>.pt).
    path(
        "runs/<slug:run_id>/for-sale/",
        views.ForSaleView.as_view(),
        name="for_sale",
    ),
]
