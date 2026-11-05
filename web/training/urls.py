from django.urls import path

from web.training import views

app_name = "training"
urlpatterns = [
    path("final-models/", views.FinalModelsView.as_view(), name="final_models"),
]
