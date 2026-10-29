"""URLconf; each slice adds its app's routes."""

from django.contrib.auth import views as auth_views
from django.urls import URLPattern, URLResolver, include, path
from django.views.generic import RedirectView

urlpatterns: list[URLPattern | URLResolver] = [
    path("", RedirectView.as_view(pattern_name="practice:index"), name="home"),
    path(
        "login/",
        auth_views.LoginView.as_view(template_name="accounts/login.html"),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("practice/", include("web.practice.urls")),
]
