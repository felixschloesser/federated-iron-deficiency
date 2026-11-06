"""URLconf; each slice adds its app's routes."""

from typing import assert_never

from django.conf import settings
from django.contrib.auth import views as auth_views
from django.urls import URLPattern, URLResolver, include, path

from web.accounts.forms import RoleAuthenticationForm
from web.accounts.views import HomeView
from web.party import Party
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


def party_urls(party: Party | None) -> list[URLResolver]:
    """The pages of one party's web app; in development, every party's."""
    match party:
        case None:
            return [url for each in Party for url in party_urls(each)]
        case Party.HOSPITAL:
            return [
                path("lab/", include("web.hospital.lab.urls")),
                path("deployment/", include("web.hospital.deployment.urls")),
                path("cohort/", include("web.hospital.cohort.urls")),
            ]
        case Party.PRACTICE:
            return [path("practice/", include("web.practice.urls"))]
        case Party.STARTUP:
            return [path("training/", include("web.startup.training.urls"))]
        case _:
            assert_never(party)


urlpatterns += party_urls(settings.PARTY)

handler500 = ServerErrorView.as_view()
