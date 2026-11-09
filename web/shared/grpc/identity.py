"""Identify the calling party. The client puts its name's slug in each call's
metadata, and the server trusts it.

A slug is ASCII whatever the name, which metadata requires and which a
certificate name would be too. With mutual TLS, which the demo leaves out, the
server would read the name from the client's certificate
(context.auth_context()) and only `caller` would change."""

import grpc
from django.utils.text import slugify

KEY = "party"

type Metadata = tuple[tuple[str, str], ...]


def calling_as(name: str) -> Metadata:
    """The metadata that names the calling party."""
    return ((KEY, slugify(name)),)


def caller(context: grpc.ServicerContext) -> str | None:
    """The slug the call named its party by, or None if it named none."""
    named = dict(context.invocation_metadata()).get(KEY)
    return named if isinstance(named, str) and named else None
