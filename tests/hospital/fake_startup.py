"""A stand-in for the startup's messaging endpoint, so the hospital's tests
need none of the startup's code: it offers the screening models it is given and
records which screening models each fetch said the hospital holds."""

from collections.abc import Iterator
from concurrent import futures
from contextlib import contextmanager
from dataclasses import dataclass, field

import grpc

from web.shared.messaging import messages_pb2, messages_pb2_grpc


def named(context: grpc.ServicerContext) -> str | None:
    """The slug a call named its party by, read as any server reads it."""
    name = dict(context.invocation_metadata()).get("party")
    return name if isinstance(name, str) else None


@dataclass
class FakeStartup(messages_pb2_grpc.ScreeningModelsServicer):
    offered: list[messages_pb2.ScreeningModel] = field(default_factory=list)
    # The run IDs each fetch said the hospital holds, in order.
    held: list[list[int]] = field(default_factory=list)
    # The slug each fetch named its party by, in order.
    callers: list[str | None] = field(default_factory=list)
    # A startup that offers what the hospital holds all the same.
    ignores_held: bool = False

    def FetchNewScreeningModels(
        self,
        request: "messages_pb2.NewScreeningModelsRequest",
        context: grpc.ServicerContext,
    ) -> messages_pb2.NewScreeningModels:
        self.callers.append(named(context))
        self.held.append(list(request.held_run_ids))
        return messages_pb2.NewScreeningModels(
            screening_models=[
                model
                for model in self.offered
                if self.ignores_held or model.run_id not in request.held_run_ids
            ]
        )


@contextmanager
def running(startup: FakeStartup) -> Iterator[str]:
    """The stand-in, serving; its address."""
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
    messages_pb2_grpc.add_ScreeningModelsServicer_to_server(startup, server)
    port = server.add_insecure_port("127.0.0.1:0")
    server.start()
    try:
        yield f"127.0.0.1:{port}"
    finally:
        server.stop(grace=None)
