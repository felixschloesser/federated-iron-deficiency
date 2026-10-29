from django.http import HttpRequest

from web.accounts.roles import role_of


def navigation(request: HttpRequest) -> dict[str, list[dict[str, str]]]:
    """The header links of the logged-in user's role."""
    role = role_of(getattr(request, "user", None))
    return {"nav_links": role.nav_links() if role else []}
