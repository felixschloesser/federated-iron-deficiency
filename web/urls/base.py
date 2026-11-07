"""The pages every party's web app has; each party's URLconf (web/urls/<party>.py,
its settings' ROOT_URLCONF) adds its own."""

from django.contrib.auth import views as auth_views
from django.urls import URLPattern, URLResolver, path

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
]


handler500 = ServerErrorView.as_view()
