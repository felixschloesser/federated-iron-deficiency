"""A stand-in for the startup's final-models endpoint, so the hospital's tests
need none of the startup's code: it offers the final models it is given and
records which ones the hospital acknowledged."""

from collections.abc import Iterator
from concurrent import futures
from contextlib import contextmanager
from dataclasses import dataclass, field

import grpc

from web.messaging import messages_pb2, messages_pb2_grpc


@dataclass
class FakeStartup(messages_pb2_grpc.FinalModelsServicer):
    offered: list[messages_pb2.FinalModel] = field(default_factory=list)
    acknowledged: list[str] = field(default_factory=list)
    certificate_names: list[str] = field(default_factory=list)

    def FetchNewFinalModels(
        self, request: messages_pb2.NewFinalModelsRequest, context: grpc.ServicerContext
    ) -> messages_pb2.FinalModels:
        self.certificate_names.append(request.certificate_name)
        return messages_pb2.FinalModels(
            final_models=[
                model for model in self.offered if model.run_id not in self.acknowledged
            ]
        )

    def AcknowledgeFinalModels(
        self,
        request: messages_pb2.FinalModelAcknowledgement,
        context: grpc.ServicerContext,
    ) -> messages_pb2.Received:
        self.acknowledged.extend(request.run_ids)
        return messages_pb2.Received()


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
