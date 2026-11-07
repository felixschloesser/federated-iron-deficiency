"""Who is calling: the client names itself by its certificate name in each call's
metadata, and the server believes it (web/shared/messaging/messages.proto). With
the report's mutual TLS the server would read the name from the client's
certificate, context.auth_context(), and only `caller` would change."""

import grpc
from django.core.exceptions import ImproperlyConfigured

KEY = "certificate-name"

type Metadata = tuple[tuple[str, str], ...]


def calling_as(certificate_name: str | None) -> Metadata:
    """The metadata a call names its party by; a party nobody named cannot call."""
    if not certificate_name:
        raise ImproperlyConfigured("Calling another party needs a certificate name.")
    return ((KEY, certificate_name),)


def caller(context: grpc.ServicerContext) -> str | None:
    """The certificate name the call named itself by; None when it named none."""
    named = dict(context.invocation_metadata()).get(KEY)
    return named if isinstance(named, str) and named else None
