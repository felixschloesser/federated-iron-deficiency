"""How a caller names its party: its name's slug in each call's metadata
(web/shared/grpc/identity.py)."""

import pytest
from django.core.exceptions import ImproperlyConfigured


@pytest.mark.parametrize(
    ("name", "slug"),
    [
        ("Huisartsenpraktijk De Ceder", "huisartsenpraktijk-de-ceder"),
        ("CHU Liège", "chu-liege"),
    ],
)
def test_a_caller_names_its_party_by_its_names_slug(name: str, slug: str) -> None:
    """One metadata entry, ASCII whatever the name, as metadata requires."""
    from web.shared.grpc.identity import calling_as

    assert calling_as(name) == (("party", slug),)


@pytest.mark.parametrize("name", [None, "", "!!!"])
def test_a_party_without_a_name_cannot_call(name: str | None) -> None:
    """A party nobody named, or whose name has no slug, claims none at all: a
    configuration fault."""
    from web.shared.grpc.identity import calling_as

    with pytest.raises(ImproperlyConfigured):
        calling_as(name)
