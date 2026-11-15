import numpy as np
import pandas as pd

from src import main as runner


def test_t02_pipeline_writes_ranked_predictions_and_review_queue(tmp_path):
    out = tmp_path / "poc"
    result = runner.main([
        "--track", "t02",
        "--output", str(out),
        "--offline",
        "--seed", "42",
    ])

    assert result == 0
    predictions = pd.read_csv(out / "ranked_review.csv")
    queue = pd.read_csv(out / "review_queue.csv")
    assert len(predictions) == 96
    assert predictions["image_id"].is_unique
    assert {"image_id", "score"}.issubset(predictions.columns)
    assert np.isfinite(predictions["score"]).all()
    assert len(queue) == 20
    assert (out / "contact_sheet.html").is_file()
