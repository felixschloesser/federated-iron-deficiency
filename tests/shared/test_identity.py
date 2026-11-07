"""How a caller names itself: the certificate name in each call's metadata
(web/shared/messaging/identity.py)."""

import pytest
from django.core.exceptions import ImproperlyConfigured


def test_a_caller_names_itself_in_one_metadata_entry() -> None:
    """The claimed name travels as one metadata entry, nothing else beside it."""
    from web.shared.messaging.identity import calling_as

    assert calling_as("de-ceder") == (("certificate-name", "de-ceder"),)


@pytest.mark.parametrize("name", [None, ""])
def test_a_party_without_a_certificate_name_cannot_call(name: str | None) -> None:
    """A party nobody named claims no name at all: it is a configuration fault."""
    from web.shared.messaging.identity import calling_as

    with pytest.raises(ImproperlyConfigured):
        calling_as(name)
