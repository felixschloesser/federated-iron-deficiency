"""The startup's copy of every final model (DS4), as its data scientist sees it."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from iron_deficiency.screening import from_bytes


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
