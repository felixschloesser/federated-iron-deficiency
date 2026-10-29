from django.urls import path

from web.practice import views

app_name = "practice"
urlpatterns = [
    path("", views.OrderIndexView.as_view(), name="index"),
    path("orders/new/", views.NewOrderView.as_view(), name="new_order"),
]
