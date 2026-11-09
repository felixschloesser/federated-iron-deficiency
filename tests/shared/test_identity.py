"""How a caller names its party: its name's slug in each call's metadata
(web/shared/grpc/identity.py)."""

import pytest


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
