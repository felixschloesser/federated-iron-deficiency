"""A screening model enters the hospital only when its laboratory director
fetches new screening models: the hospital's own code asks the startup's
messaging endpoint, saying which screening models it holds, and stores each with its local
validation (model_files.py) (web/shared/messaging/messages.proto,
features/hospital/fetch.feature). The startup's code at the hospital writes
nothing here."""

from dataclasses import dataclass
from datetime import datetime

import grpc
import pandas as pd
import protovalidate
import torch
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from ml.final_model import model_file_paths, weights_from_bytes
from ml.training_cohort import (
    TrainingCohortUnavailable,
    read_training_cohort,
    training_cohorts,
)
from web.hospital.deployment.model_files import store_fetched
from web.shared.messaging import messages_pb2, messages_pb2_grpc
from web.shared.messaging.identity import calling_as

TIMEOUT_SECONDS = 30


def unreachable(error: grpc.RpcError) -> bool:
    """Whether the startup could not be reached, rather than refused the request."""
    return error.code() in {
        grpc.StatusCode.UNAVAILABLE,
        grpc.StatusCode.DEADLINE_EXCEEDED,
    }


@dataclass(frozen=True)
class OfferedScreeningModel:
    """A screening model as the startup sends it (DF37), every part present and its
    weights read."""

    run_id: int
    state_dict: dict[str, torch.Tensor]
    federated_auroc: float


def offered_screening_model(
    message: messages_pb2.ScreeningModel,
) -> OfferedScreeningModel | None:
    """The screening model a message holds; None if it breaks the contract or its
    weights are unreadable or do not fit the network."""
    if protovalidate.collect_violations(message):
        return None
    state_dict = weights_from_bytes(message.weights)
    if state_dict is None:
        return None
    return OfferedScreeningModel(
        run_id=message.run_id,
        state_dict=state_dict,
        federated_auroc=message.federated_auroc,
    )


def fetch_screening_models(*, now: datetime) -> list[int]:
    """Fetch the screening models this hospital does not hold, telling the
    startup which it holds, validate each complete one on the training cohort its laboratory
    director provided and store it; the run IDs stored. One the hospital holds
    other weights for is never overwritten. Raises TrainingCohortUnavailable,
    before asking the startup, when no training cohort was provided, and
    grpc.RpcError when the startup cannot be reached or refuses."""
    address, directory = settings.STARTUP_ADDRESS, settings.SCREENING_MODELS_DIR
    cohort_dir = settings.TRAINING_COHORT_DIR
    if address is None or directory is None or cohort_dir is None:
        raise ImproperlyConfigured(
            "Fetching needs STARTUP_ADDRESS, the screening models' folder and the"
            " training cohort's."
        )
    metadata = calling_as(settings.HOSPITAL_NAME)
    if not training_cohorts(cohort_dir):
        raise TrainingCohortUnavailable("No training cohort to validate on.")
    with grpc.insecure_channel(address) as channel:
        startup = messages_pb2_grpc.ScreeningModelsStub(channel)
        held = [int(path.stem) for path in model_file_paths(directory)]
        offered = startup.FetchNewScreeningModels(
            messages_pb2.NewScreeningModelsRequest(held_run_ids=held),
            timeout=TIMEOUT_SECONDS,
            metadata=metadata,
        ).screening_models
        cohort: pd.DataFrame | None = None
        stored = []
        for message in offered:
            model = offered_screening_model(message)
            if model is None:
                continue
            if cohort is None:
                _, cohort = read_training_cohort(cohort_dir, None)
            try:
                store_fetched(
                    directory,
                    run_id=model.run_id,
                    state_dict=model.state_dict,
                    cohort=cohort,
                    federated_auroc=model.federated_auroc,
                    stored_at=now,
                )
            except FileExistsError:
                continue
            stored.append(model.run_id)
    return stored
