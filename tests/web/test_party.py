"""Each kind of deployment serves only its own party's pages (spec §9)."""

import pytest

from web.party import Party
from web.urls import party_urls


def prefixes(party: Party | None) -> set[str]:
    return {str(pattern.pattern) for pattern in party_urls(party)}


@pytest.mark.parametrize("party", Party)
def test_every_party_serves_pages(party: Party) -> None:
    assert prefixes(party)


def test_a_hospital_serves_no_general_practitioner_pages() -> None:
    assert prefixes(Party.HOSPITAL) == {"lab/", "deployment/"}


def test_a_practice_serves_no_hospital_pages() -> None:
    assert prefixes(Party.GENERAL_PRACTITIONER) == {"practice/"}


def test_the_startup_serves_only_its_training_pages() -> None:
    assert prefixes(Party.STARTUP) == {"training/"}


def test_development_serves_every_party() -> None:
    assert prefixes(None) == {prefix for party in Party for prefix in prefixes(party)}
