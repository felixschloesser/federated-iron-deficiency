"""The pages every party's web app has. Each party's own URLconf
(web/<party>/urls.py, its settings' ROOT_URLCONF) adds its pages."""

from django.contrib.auth import views as auth_views
from django.urls import URLPattern, URLResolver, path

from web.shared.accounts.forms import RoleAuthenticationForm
from web.shared.accounts.views import HomeView
from web.shared.views import ServerErrorView

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
