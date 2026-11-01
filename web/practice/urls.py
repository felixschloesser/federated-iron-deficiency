from django.urls import path, register_converter

from web.practice import views
from web.practice.converters import TestConverter

register_converter(TestConverter, "test")

app_name = "practice"
urlpatterns = [
    path("patients/", views.PatientIndexView.as_view(), name="patients"),
    path("patients/<int:pk>/", views.PatientDetailView.as_view(), name="patient"),
    path(
        "patients/<int:patient>/orders/new/<test:test>/",
        views.NewOrderView.as_view(),
        name="new_order",
    ),
    path(
        "patients/<int:patient>/samples/<int:sample>/orders/new/<test:test>/",
        views.NewOrderView.as_view(),
        name="new_order_on_sample",
    ),
    path("orders/", views.OrderIndexView.as_view(), name="orders"),
    path(
        "orders/check-for-reports/",
        views.CheckForReportsView.as_view(),
        name="check_for_reports",
    ),
]
