from django.urls import path

from web.training import views

app_name = "training"
urlpatterns = [
    path("final-models/", views.FinalModelsView.as_view(), name="final_models"),
    # slug: a run ID never holds a path separator (the file is <run_id>.pt).
    path(
        "final-models/<slug:run_id>/for-sale/",
        views.ForSaleView.as_view(),
        name="for_sale",
    ),
]
