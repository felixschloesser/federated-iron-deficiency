"""Local screening with a final model, outside the web app."""

from pathlib import Path

import pandas as pd

from iron_deficiency.cohort import CBC_VARS, FEATURES
from iron_deficiency.screening import FinalModel, screen, standardization_tensor
from iron_deficiency.task import Net


def test_screen_scores_only_eligible_women_and_returns_only_decisions(
    tmp_path: Path,
) -> None:
    zeros = pd.Series(0.0, index=FEATURES)
    model = FinalModel(
        state_dict=Net().state_dict(),
        mean=standardization_tensor(zeros),
        std=standardization_tensor(zeros + 1),
    )
    samples = pd.DataFrame(
        {
            "sample_id": [1, 2, 3],
            "sex": ["Female", "Male", "Female"],
            "age": [30, 30, 60],
            **{var: [1.0] * 3 for var in CBC_VARS},
            "name": ["A", "B", "C"],  # A lab export may carry more than needed
        }
    )

    results = screen(samples, model, threshold=0.5)

    assert list(results.columns) == ["sample_id", "result"]
    assert results["result"].iat[0] in {"flagged", "not flagged"}
    assert results["result"].iloc[1:].tolist() == ["not screened"] * 2
