from django.http import HttpRequest

from web.shared.accounts.roles import role_of


def navigation(request: HttpRequest) -> dict[str, list[dict[str, str | bool]]]:
    """The header links for the logged-in user's role. A link is current when this
    page is its page or lies under it, so a patient's page marks Patients."""
    role = role_of(getattr(request, "user", None))
    links = role.nav_links() if role else []
    holding = [link for link in links if request.path.startswith(link["url"])]
    # /lab/test-requests/analysed/ also lies under /lab/test-requests/, so the longest match is current.
    current = max(holding, key=lambda link: len(link["url"]), default=None)
    return {"nav_links": [{**link, "current": link is current} for link in links]}
