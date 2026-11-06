"""The startup's copy of every final model (DS4), as its data scientist sees it."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import assert_never

from django.db import models

from ml.screening import (
    FinalModel,
    final_model_path,
    final_model_paths,
    from_bytes,
    to_bytes,
)
from web.training.forms import SubmitRunForm
from web.training.models import Transmission
from web.training.runs import RunStatus, TrainingRun


@dataclass(frozen=True)
class KeptFinalModel:
    """A final model as the startup kept it; any part an older file lacks is None."""

    run_id: str
    stored_at: datetime | None
    federated_auroc: float | None
    run_configuration: dict[str, int | float]

    @property
    def run_configuration_items(self) -> list[tuple[str, int | float]]:
        """The parameters the data scientist chose, in the form's words and order."""
        return [
            (str(field.label), self.run_configuration[key])
            for name, field in SubmitRunForm.base_fields.items()
            if (key := name.replace("_", "-")) in self.run_configuration
        ]

    @property
    def run_configuration_shown(self) -> str | None:
        """The same on one line."""
        shown = [f"{label} {value}" for label, value in self.run_configuration_items]
        return ", ".join(shown) or None


def final_models(directory: Path | None) -> list[KeptFinalModel]:
    """Every final model the startup kept, newest first."""
    if directory is None or not directory.is_dir():
        return []
    kept = []
    for path in final_model_paths(directory):
        model = from_bytes(path.read_bytes())
        kept.append(
            KeptFinalModel(
                run_id=path.stem,
                stored_at=model.stored_at,
                federated_auroc=model.federated.get("eval_auroc"),
                run_configuration=model.run_configuration,
            )
        )
    return sorted(
        kept,
        key=lambda model: (model.stored_at is not None, model.stored_at),
        reverse=True,
    )


def for_sale(directory: Path | None, run_id: str) -> bytes | None:
    """A final model as the startup sells it (DF16): its weights only, in the final
    model file format; a buyer standardizes on its own cohort and chooses its
    threshold there, as each hospital does. None for a run the startup kept no
    readable model of."""
    path = None if directory is None else final_model_path(directory, run_id)
    if path is None or not path.is_file():
        return None
    model = from_bytes(path.read_bytes())
    if model.state_dict is None:
        return None
    return to_bytes(FinalModel(state_dict=model.state_dict))


class TransmissionStatus(models.TextChoices):
    """Whether a final model reached the hospitals, from its latest transmission's
    run status (features/training.feature)."""

    NOT_TRANSMITTED = "not_transmitted", "Not transmitted"
    TRANSMITTING = "transmitting", "Transmitting"
    TRANSMITTED = "transmitted", "Transmitted"
    NOT_EVERY_HOSPITAL = "not_every_hospital", "Not transmitted to every hospital"
    UNKNOWN = "unknown", "Status unknown"

    @classmethod
    def of_run(cls, status: RunStatus | None) -> "TransmissionStatus":
        """A transmission's status from its run's status; None for a status this
        app does not know."""
        match status:
            case None:
                return cls.UNKNOWN
            case RunStatus.PENDING | RunStatus.STARTING | RunStatus.RUNNING:
                return cls.TRANSMITTING
            case RunStatus.COMPLETED:
                return cls.TRANSMITTED
            case RunStatus.FAILED | RunStatus.STOPPED:
                return cls.NOT_EVERY_HOSPITAL
            case _:
                assert_never(status)

    @property
    def offers_transmit(self) -> bool:
        """Whether Transmit is offered: not while a transmission is under way or
        its status unknown; again after one completed, for a hospital that was not
        connected (receiving is idempotent)."""
        match self:
            case (
                TransmissionStatus.NOT_TRANSMITTED
                | TransmissionStatus.TRANSMITTED
                | TransmissionStatus.NOT_EVERY_HOSPITAL
            ):
                return True
            case TransmissionStatus.TRANSMITTING | TransmissionStatus.UNKNOWN:
                return False
            case _:
                assert_never(self)


def transmission_statuses(
    kept: list[KeptFinalModel],
    runs: list[TrainingRun] | None,
    transmissions: list[Transmission],
) -> dict[str, TransmissionStatus]:
    """Each kept final model's transmission status, from its latest transmission; runs is
    None when the SuperLink did not answer, so a transmission's status is
    unknown."""
    latest = {
        transmission.final_model: transmission
        for transmission in sorted(
            transmissions, key=lambda each: (each.submitted_at, each.pk)
        )
    }
    statuses = {run.run_id: run for run in runs or []}
    shown = {}
    for model in kept:
        transmission = latest.get(model.run_id)
        if transmission is None:
            shown[model.run_id] = TransmissionStatus.NOT_TRANSMITTED
            continue
        run = statuses.get(int(transmission.run_id)) if runs is not None else None
        shown[model.run_id] = (
            TransmissionStatus.UNKNOWN
            if run is None
            else TransmissionStatus.of_run(run.status)
        )
    return shown
