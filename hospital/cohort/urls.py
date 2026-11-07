from django.urls import path

from hospital.cohort import views

app_name = "cohort"
urlpatterns = [
    path("", views.TrainingCohortView.as_view(), name="training_cohort"),
    path("provide/", views.ProvideView.as_view(), name="provide"),
    path("withdraw/", views.WithdrawView.as_view(), name="withdraw"),
]
