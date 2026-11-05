"""The startup's copy of every final model (DS4), as its data scientist sees it."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from iron_deficiency.screening import FinalModel, final_model_path, from_bytes, to_bytes


@dataclass(frozen=True)
class KeptFinalModel:
    """A final model as the startup kept it; any part an older file lacks is None."""

    run_id: str
    stored_at: datetime | None
    threshold: float | None
    federated_auroc: float | None


def final_models(directory: Path | None) -> list[KeptFinalModel]:
    """Every final model the startup kept, newest first."""
    if directory is None or not directory.is_dir():
        return []
    kept = []
    for path in directory.glob("*.pt"):
        model = from_bytes(path.read_bytes())
        kept.append(
            KeptFinalModel(
                run_id=path.stem,
                stored_at=model.stored_at,
                threshold=model.threshold,
                federated_auroc=model.federated.get("eval_auroc"),
            )
        )
    return sorted(
        kept,
        key=lambda model: (model.stored_at is not None, model.stored_at),
        reverse=True,
    )


def for_sale(directory: Path | None, run_id: str) -> bytes | None:
    """A final model as the startup sells it (DF16): its weights and threshold,
    in the final model file format; a buyer standardizes on its own cohort, as
    each hospital does. None for a run the startup kept no readable model of."""
    path = None if directory is None else final_model_path(directory, run_id)
    if path is None or not path.is_file():
        return None
    model = from_bytes(path.read_bytes())
    if model.state_dict is None:
        return None
    return to_bytes(FinalModel(state_dict=model.state_dict, threshold=model.threshold))
