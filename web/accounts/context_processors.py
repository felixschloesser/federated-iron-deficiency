from django.http import HttpRequest

from web.accounts.roles import role_of


def navigation(request: HttpRequest) -> dict[str, list[dict[str, str | bool]]]:
    """The header links of the logged-in user's role; the one whose page this is,
    or holds it (a patient's page under Patients), is current."""
    role = role_of(getattr(request, "user", None))
    links = role.nav_links() if role else []
    holding = [link for link in links if request.path.startswith(link["url"])]
    # /lab/orders/analysed/ is under /lab/orders/ too: the longest one is current.
    current = max(holding, key=lambda link: len(link["url"]), default=None)
    return {"nav_links": [{**link, "current": link is current} for link in links]}
