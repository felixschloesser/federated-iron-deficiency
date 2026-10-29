from django.urls import path

from web.practice import views

app_name = "practice"
urlpatterns = [
    path("", views.index, name="index"),
    path("orders/new/", views.new_order, name="new_order"),
]
