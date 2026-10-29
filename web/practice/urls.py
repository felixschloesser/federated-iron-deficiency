from django.urls import path, register_converter

from web.practice import views
from web.practice.converters import TestConverter

register_converter(TestConverter, "test")

app_name = "practice"
urlpatterns = [
    path("", views.OrderIndexView.as_view(), name="index"),
    path("orders/new/<test:test>/", views.NewOrderView.as_view(), name="new_order"),
]
