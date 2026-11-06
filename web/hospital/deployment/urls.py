from django.urls import path

from web.hospital.deployment import views

app_name = "deployment"
urlpatterns = [
    path(
        "screening-models/",
        views.ScreeningModelsView.as_view(),
        name="screening_models",
    ),
    # slug: a run ID never holds a path separator (the file is <run_id>.pt).
    path(
        "screening-models/<slug:run_id>/deploy/",
        views.DeployView.as_view(),
        name="deploy",
    ),
]
