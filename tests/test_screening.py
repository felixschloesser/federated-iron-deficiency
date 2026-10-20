"""Checks for local screening with a deployed model."""

import pandas as pd

from iron_deficiency.dataset import CBC_VARS, FEATURES
from iron_deficiency.screening import save_deployment, screen
from iron_deficiency.task import Net


def test_screen_scores_only_eligible_women_and_returns_only_decisions(tmp_path):
    model = tmp_path / "model.pt"
    zeros = pd.Series(0.0, index=FEATURES)
    save_deployment(model, Net().state_dict(), zeros, zeros + 1, threshold=0.5)
    samples = pd.DataFrame(
        {
            "sample_id": [1, 2, 3],
            "sex": ["Female", "Male", "Female"],
            "age": [30, 30, 60],
            **{var: [1.0] * 3 for var in CBC_VARS},
            "name": ["A", "B", "C"],  # A lab export may carry more than needed
        }
    )

    results = screen(samples, model)

    assert list(results.columns) == ["sample_id", "result"]
    assert results["result"].iat[0] in {"flagged", "not flagged"}
    assert results["result"].iloc[1:].tolist() == ["not screened"] * 2
