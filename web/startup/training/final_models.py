"""Reads the final models the startup keeps on disk, for its data scientist's
pages and for release to hospitals."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ml.final_model import (
    model_file_path,
    model_file_paths,
    read_final_model,
    weights_to_bytes,
)
from web.shared.grpc import messages_pb2
from web.startup.training.forms import SubmitRunForm


@dataclass(frozen=True)
class KeptFinalModel:
    """A final model as the startup kept it."""

    run_id: str
    stored_at: datetime
    federated_auroc: float
    run_configuration: dict[str, int | float]

    @property
    def run_configuration_items(self) -> list[tuple[str, int | float]]:
        """The parameters the data scientist chose, labelled and ordered as in the
        submit form."""
        return [
            (str(field.label), self.run_configuration[key])
            for name, field in SubmitRunForm.base_fields.items()
            if (key := name.replace("_", "-")) in self.run_configuration
        ]

    @property
    def run_configuration_shown(self) -> str | None:
        """The same parameters on one line, or None if there are none."""
        shown = [f"{label} {value}" for label, value in self.run_configuration_items]
        return ", ".join(shown) or None


def final_models(directory: Path) -> list[KeptFinalModel]:
    """Every readable final model the startup kept, newest first."""
    if not directory.is_dir():
        return []
    kept = [
        KeptFinalModel(
            run_id=str(model.run_id),
            stored_at=model.stored_at,
            federated_auroc=model.federated_auroc,
            run_configuration=model.run_configuration,
        )
        for path in model_file_paths(directory)
        if (model := read_final_model(path)) is not None
    ]
    return sorted(kept, key=lambda model: model.stored_at, reverse=True)


def released_final_model(
    directory: Path, run_id: str
) -> messages_pb2.ScreeningModel | None:
    """A released final model as a recipient hospital fetches it: its weights,
    the AUROC across hospitals and its run ID, but never its run configuration.
    None if the startup has no readable model for that run."""
    path = model_file_path(directory, run_id)
    model = read_final_model(path) if path.is_file() else None
    if model is None:
        return None
    return messages_pb2.ScreeningModel(
        run_id=model.run_id,
        weights=weights_to_bytes(model.state_dict),
        federated_auroc=model.federated_auroc,
    )
