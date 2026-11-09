"""The startup's copy of every final model (DS4), as its data scientist sees it."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ml.final_model import (
    final_model_path,
    final_model_paths,
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
    """Every readable final model the startup kept, newest first."""
    if directory is None or not directory.is_dir():
        return []
    kept = [
        KeptFinalModel(
            run_id=str(model.run_id),
            stored_at=model.stored_at,
            federated_auroc=model.federated_auroc,
            run_configuration=model.run_configuration,
        )
        for path in final_model_paths(directory)
        if (model := read_final_model(path)) is not None
    ]
    return sorted(kept, key=lambda model: model.stored_at, reverse=True)


def released_final_model(
    directory: Path | None, run_id: str
) -> messages_pb2.FinalModel | None:
    """A released final model as a recipient hospital fetches it (DF33): its
    weights only, the AUROC across hospitals, and its run ID; never its run
    configuration. None for a run the startup kept no readable model of."""
    path = None if directory is None else final_model_path(directory, run_id)
    model = None if path is None or not path.is_file() else read_final_model(path)
    if model is None:
        return None
    return messages_pb2.FinalModel(
        run_id=model.run_id,
        weights=weights_to_bytes(model.state_dict),
        federated_auroc=model.federated_auroc,
    )
