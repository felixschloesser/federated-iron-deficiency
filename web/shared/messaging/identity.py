"""Who is calling: the client calls as its name's slug, in each call's metadata,
and the server believes it (web/shared/messaging/messages.proto). The slug follows
from the name, so it is ASCII whatever the name: what metadata allows, and what a
certificate would carry. With the report's mutual TLS the server would read it
from the client's certificate, context.auth_context(), and only `caller` would
change."""

import grpc
from django.core.exceptions import ImproperlyConfigured
from django.utils.text import slugify

KEY = "party"

type Metadata = tuple[tuple[str, str], ...]


def calling_as(name: str | None) -> Metadata:
    """The metadata a call names its party by; a party nobody named cannot call."""
    if not name or not slugify(name):
        raise ImproperlyConfigured("Calling another party needs its name.")
    return ((KEY, slugify(name)),)


def caller(context: grpc.ServicerContext) -> str | None:
    """The slug the call named its party by; None when it named none."""
    named = dict(context.invocation_metadata()).get(KEY)
    return named if isinstance(named, str) and named else None
