"""The startup's screening-models endpoint (P5): a released final model reaches a
hospital as a screening model; a recipient hospital fetches the screening
models it does not hold, saying which it holds
(web/shared/grpc/messages.proto, features/startup/release.feature)."""

import grpc
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

from web.shared.grpc import messages_pb2, messages_pb2_grpc
from web.shared.grpc.endpoint import start, with_database
from web.shared.grpc.identity import caller
from web.shared.grpc.rejection import rejected
from web.shared.parsing import once_each
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
        request: messages_pb2.FetchNewScreeningModelsRequest,
        context: grpc.ServicerContext,
    ) -> messages_pb2.FetchNewScreeningModelsResponse:
        recipient = recipient_of(context)
        try:
            once_each("held_run_ids", request.held_run_ids, code="duplicate_run_id")
        except ValidationError as error:
            context.abort_with_status(rejected(error))
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
        # Only a hospital still waiting gets the reply. One lost after this check
        # is still recorded; the hospital's held list then has it sent again.
        if context.is_active():
            Release.objects.record_fetched(
                recipient=recipient,
                run_ids=[str(model.run_id) for model in offered],
                now=timezone.now(),
            )
        return messages_pb2.FetchNewScreeningModelsResponse(screening_models=offered)


def serve(address: str) -> tuple[grpc.Server, int]:
    """Start the endpoint on `address`; the server and its port."""
    return start(
        address,
        lambda server: messages_pb2_grpc.add_ScreeningModelsServicer_to_server(
            ScreeningModelsService(), server
        ),
    )
