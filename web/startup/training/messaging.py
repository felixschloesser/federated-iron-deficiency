"""The startup's messaging endpoint (P5): a released final model reaches a
hospital as a screening model; a recipient hospital fetches the screening
models it does not hold, saying which it holds
(web/shared/messaging/messages.proto, features/startup/release.feature)."""

import grpc
from django.conf import settings
from django.utils import timezone

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


class ScreeningModelsService(messages_pb2_grpc.ScreeningModelsServicer):
    """Hands out screening models, like a view: who asks, then what they get."""

    @with_database
    def FetchNewScreeningModels(
        self,
        request: messages_pb2.NewScreeningModelsRequest,
        context: grpc.ServicerContext,
    ) -> messages_pb2.NewScreeningModels:
        recipient = recipient_of(context)
        held = [str(run_id) for run_id in request.held_run_ids]
        offered = [
            model
            for release in Release.objects.not_held(held)
            if (
                model := released_final_model(
                    settings.FINAL_MODELS_DIR, release.final_model_run_id
                )
            )
            is not None
        ]
        Release.objects.record_fetched(
            recipient=recipient,
            run_ids=[str(model.run_id) for model in offered],
            now=timezone.now(),
        )
        return messages_pb2.NewScreeningModels(screening_models=offered)


def serve(address: str) -> tuple[grpc.Server, int]:
    """Start the endpoint on `address`; the server and its port."""
    return start(
        address,
        lambda server: messages_pb2_grpc.add_ScreeningModelsServicer_to_server(
            ScreeningModelsService(), server
        ),
    )
