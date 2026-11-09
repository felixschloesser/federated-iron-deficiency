"""Fetching new screening models from the startup (web/shared/grpc/messages.proto,
features/hospital/fetch.feature).

A screening model enters the hospital only when its laboratory director fetches
new screening models. The hospital's own code then calls the startup's
screening-models endpoint, says which screening models it already holds, and
stores each new one with its local validation (model_files.py). The startup's
code running at the hospital writes nothing here."""

from dataclasses import dataclass
from datetime import datetime

import grpc
import pandas as pd
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
from web.shared.grpc import messages_pb2, messages_pb2_grpc
from web.shared.grpc.identity import calling_as

TIMEOUT_SECONDS = 30


def unreachable(error: grpc.RpcError) -> bool:
    """Whether the startup could not be reached, rather than refused the request."""
    return error.code() in {
        grpc.StatusCode.UNAVAILABLE,
        grpc.StatusCode.DEADLINE_EXCEEDED,
    }


@dataclass(frozen=True)
class OfferedScreeningModel:
    """A screening model as the startup sends it, with every part present and its
    weights already read."""

    run_id: int
    state_dict: dict[str, torch.Tensor]
    federated_auroc: float


def offered_screening_model(
    message: messages_pb2.ScreeningModel,
) -> OfferedScreeningModel | None:
    """The screening model in a message, or None if a part is missing or its
    weights are unreadable or do not fit the network."""
    if not message.run_id or not message.HasField("federated_auroc"):
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
    """Fetch the screening models this hospital does not hold yet, validate each
    complete one on the provided training cohort, store it, and return the run
    IDs stored.

    The request tells the startup which screening models the hospital holds. A
    stored model is never overwritten with other weights. Raises
    TrainingCohortUnavailable, before calling the startup, when no training
    cohort is provided, and grpc.RpcError when the startup cannot be reached or
    refuses."""
    address, directory = settings.STARTUP_ADDRESS, settings.SCREENING_MODELS_DIR
    cohort_dir = settings.TRAINING_COHORT_DIR
    if address is None:
        raise ImproperlyConfigured("Fetching needs STARTUP_ADDRESS.")
    metadata = calling_as(settings.PARTY_NAME)
    if not training_cohorts(cohort_dir):
        raise TrainingCohortUnavailable("No training cohort to validate on.")
    with grpc.insecure_channel(address) as channel:
        startup = messages_pb2_grpc.ScreeningModelsStub(channel)
        held = [int(path.stem) for path in model_file_paths(directory)]
        offered = startup.FetchNewScreeningModels(
            messages_pb2.FetchNewScreeningModelsRequest(held_run_ids=held),
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
