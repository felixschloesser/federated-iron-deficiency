"""The startup's screening-models gRPC endpoint. A recipient hospital says which
screening models it holds and fetches the released final models it does not
hold yet (web/shared/grpc/messages.proto, features/startup/release.feature)."""

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
    """Return the calling hospital, found by the slug the call names. A call
    that names no hospital, or one the startup does not know, is aborted before
    anything is read."""
    slug = caller(context)
    if slug is None:
        context.abort(grpc.StatusCode.UNAUTHENTICATED, "hospital_required")
    recipient = Recipient.objects.filter(slug=slug).first()
    if recipient is None:
        context.abort(grpc.StatusCode.PERMISSION_DENIED, "unknown_hospital")
    return recipient


class ScreeningModelsService(messages_pb2_grpc.ScreeningModelsServicer):
    """Serves screening models: it identifies the calling hospital, then sends
    the released final models that hospital does not hold."""

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
        # Record the fetch only if the hospital is still waiting for the reply.
        # If the reply is lost after this check, the fetch is recorded anyway,
        # but the hospital's held list will not name the model, so it is sent
        # again on the next fetch.
        if context.is_active():
            Release.objects.record_fetched(
                recipient=recipient,
                run_ids=[str(model.run_id) for model in offered],
                now=timezone.now(),
            )
        return messages_pb2.FetchNewScreeningModelsResponse(screening_models=offered)


def serve(address: str) -> tuple[grpc.Server, int]:
    """Start the endpoint on `address`; return the server and its port."""
    return start(
        address,
        lambda server: messages_pb2_grpc.add_ScreeningModelsServicer_to_server(
            ScreeningModelsService(), server
        ),
    )
