"""A final model enters the hospital only when its laboratory director fetches
new final models: the hospital's own code asks the startup's final-models
endpoint, validates each final model on the hospital's validation split,
stores it and acknowledges it (web/messaging/messages.proto,
features/hospital/fetch.feature). The startup's code at the hospital writes
nothing here."""

from datetime import datetime

import grpc
import pandas as pd
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from ml.final_model import from_bytes
from ml.training_cohort import read_training_cohort
from ml.validation import receive_final_model
from web.messaging import messages_pb2, messages_pb2_grpc

TIMEOUT_SECONDS = 30


def unreachable(error: grpc.RpcError) -> bool:
    """Whether the startup could not be reached, rather than refused the request."""
    return error.code() in {
        grpc.StatusCode.UNAVAILABLE,
        grpc.StatusCode.DEADLINE_EXCEEDED,
    }


def fetch_final_models(*, now: datetime) -> list[str]:
    """Fetch the released final models this hospital has not stored, validate
    each on the training cohort its laboratory director provided, store it, then
    acknowledge them; the run IDs stored. One the hospital holds other weights
    for is never overwritten, nor acknowledged. Raises grpc.RpcError when the
    startup cannot be reached or refuses."""
    address, directory = settings.STARTUP_ADDRESS, settings.SCREENING_MODELS_DIR
    cohort_dir = settings.TRAINING_COHORT_DIR
    certificate_name = settings.HOSPITAL_CERTIFICATE_NAME
    if address is None or directory is None or cohort_dir is None:
        raise ImproperlyConfigured(
            "Fetching needs STARTUP_ADDRESS, the screening models' folder and the"
            " training cohort's."
        )
    with grpc.insecure_channel(address) as channel:
        startup = messages_pb2_grpc.FinalModelsStub(channel)
        offered = startup.FetchNewFinalModels(
            messages_pb2.NewFinalModelsRequest(certificate_name=certificate_name),
            timeout=TIMEOUT_SECONDS,
        ).final_models
        cohort: pd.DataFrame | None = None
        stored = []
        for model in offered:
            state_dict = from_bytes(model.weights).state_dict
            if state_dict is None:
                continue
            if cohort is None:
                _, cohort = read_training_cohort(cohort_dir, None)
            try:
                receive_final_model(
                    directory,
                    run_id=int(model.run_id),
                    state_dict=state_dict,
                    cohort=cohort,
                    federated=dict(model.federated),
                    stored_at=now,
                )
            except FileExistsError:
                continue
            stored.append(model.run_id)
        if stored:
            startup.AcknowledgeFinalModels(
                messages_pb2.FinalModelAcknowledgement(
                    certificate_name=certificate_name, run_ids=stored
                ),
                timeout=TIMEOUT_SECONDS,
            )
    return stored
