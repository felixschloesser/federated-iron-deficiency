"""The startup's final-models endpoint (P5): a recipient hospital fetches the
released final models it has not stored yet, and acknowledges those it stored
(web/shared/messaging/messages.proto, features/startup/release.feature)."""

import grpc
from django.conf import settings
from django.utils import timezone
from google.protobuf.empty_pb2 import Empty

from web.shared.messaging import messages_pb2, messages_pb2_grpc
from web.shared.messaging.endpoint import start, with_database
from web.shared.messaging.identity import caller
from web.startup.training.final_models import released_final_model
from web.startup.training.models import Recipient, Release


def recipient_of(context: grpc.ServicerContext) -> Recipient:
    """The calling hospital, by the slug the call names it by; a call that names
    none, or a hospital the startup does not know, is refused before anything is
    read."""
    slug = caller(context)
    if slug is None:
        context.abort(grpc.StatusCode.UNAUTHENTICATED, "hospital_required")
    recipient = Recipient.objects.filter(slug=slug).first()
    if recipient is None:
        context.abort(grpc.StatusCode.PERMISSION_DENIED, "unknown_hospital")
    return recipient


class FinalModelsService(messages_pb2_grpc.FinalModelsServicer):
    """Hands out released final models, like a view: who asks, then what they get."""

    @with_database
    def FetchNewFinalModels(
        self, request: Empty, context: grpc.ServicerContext
    ) -> messages_pb2.NewFinalModels:
        recipient = recipient_of(context)
        offered = (
            released_final_model(settings.FINAL_MODELS_DIR, release.final_model_run_id)
            for release in Release.objects.new_for(recipient)
        )
        return messages_pb2.NewFinalModels(
            final_models=[model for model in offered if model is not None]
        )

    @with_database
    def AcknowledgeFinalModels(
        self,
        request: messages_pb2.FinalModelAcknowledgement,
        context: grpc.ServicerContext,
    ) -> Empty:
        Release.objects.acknowledge(
            recipient=recipient_of(context),
            run_ids=list(request.run_ids),
            now=timezone.now(),
        )
        return Empty()


def serve(address: str) -> tuple[grpc.Server, int]:
    """Start the endpoint on `address`; the server and its port."""
    return start(
        address,
        lambda server: messages_pb2_grpc.add_FinalModelsServicer_to_server(
            FinalModelsService(), server
        ),
    )
