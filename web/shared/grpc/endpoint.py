"""Helpers every gRPC endpoint shares: managing the database connection around
each call, and starting the server. The server is plaintext: the demo leaves out
mutual TLS."""

import functools
from collections.abc import Callable
from concurrent import futures

import grpc
from django.db import close_old_connections


def with_database[**P, R](handler: Callable[P, R]) -> Callable[P, R]:
    """Close stale database connections before and after a call, as Django does around each request."""

    @functools.wraps(handler)
    def handle(*args: P.args, **kwargs: P.kwargs) -> R:
        close_old_connections()
        try:
            return handler(*args, **kwargs)
        finally:
            close_old_connections()

    return handle


def start(
    address: str, register: Callable[[grpc.Server], None]
) -> tuple[grpc.Server, int]:
    """Start a server on `address` with the services `register` adds. Returns the
    server and the port it listens on."""
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    register(server)
    port = server.add_insecure_port(address)
    server.start()
    return server, port
