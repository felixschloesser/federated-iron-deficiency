"""URLconf; each slice adds its app's routes."""

from django.contrib.auth import views as auth_views
from django.urls import URLPattern, URLResolver, include, path

from web.accounts.forms import RoleAuthenticationForm
from web.accounts.views import HomeView
from web.views import ServerErrorView

urlpatterns: list[URLPattern | URLResolver] = [
    path("", HomeView.as_view(), name="home"),
    path(
        "login/",
        auth_views.LoginView.as_view(
            template_name="accounts/login.html",
            authentication_form=RoleAuthenticationForm,
        ),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("practice/", include("web.practice.urls")),
    path("lab/", include("web.lab.urls")),
]

handler500 = ServerErrorView.as_view()
