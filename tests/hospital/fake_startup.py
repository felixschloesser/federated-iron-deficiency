"""A stand-in for the startup's final-models endpoint, so the hospital's tests
need none of the startup's code: it offers the final models it is given and
records which ones the hospital acknowledged."""

from collections.abc import Iterator
from concurrent import futures
from contextlib import contextmanager
from dataclasses import dataclass, field

import grpc
from google.protobuf.empty_pb2 import Empty

from web.shared.messaging import messages_pb2, messages_pb2_grpc


def named(context: grpc.ServicerContext) -> str | None:
    """The certificate name a call named itself by, read as any server reads it."""
    name = dict(context.invocation_metadata()).get("certificate-name")
    return name if isinstance(name, str) else None


@dataclass
class FakeStartup(messages_pb2_grpc.FinalModelsServicer):
    offered: list[messages_pb2.FinalModel] = field(default_factory=list)
    acknowledged: list[str] = field(default_factory=list)
    # The certificate name each fetch named itself by, in order.
    callers: list[str | None] = field(default_factory=list)

    def FetchNewFinalModels(
        self, request: Empty, context: grpc.ServicerContext
    ) -> messages_pb2.NewFinalModels:
        self.callers.append(named(context))
        return messages_pb2.NewFinalModels(
            final_models=[
                model for model in self.offered if model.run_id not in self.acknowledged
            ]
        )

    def AcknowledgeFinalModels(
        self,
        request: messages_pb2.FinalModelAcknowledgement,
        context: grpc.ServicerContext,
    ) -> Empty:
        self.acknowledged.extend(request.run_ids)
        return Empty()


@contextmanager
def running(startup: FakeStartup) -> Iterator[str]:
    """The stand-in, serving; its address."""
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
    messages_pb2_grpc.add_FinalModelsServicer_to_server(startup, server)
    port = server.add_insecure_port("127.0.0.1:0")
    server.start()
    try:
        yield f"127.0.0.1:{port}"
    finally:
        server.stop(grace=None)
