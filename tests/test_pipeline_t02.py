import json

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

    reviewed = queue.copy()
    reviewed["reviewer"] = "Nguyen Tuan Hung"
    reviewed["reviewer_decision"] = "reject"
    reviewed["review_note"] = "Manual review"
    reviewed["reviewed_at"] = "2026-11-15T08:20:05Z"
    reviewed.to_csv(out / "review_queue_reviewed.csv", index=False)

    result = runner.main([
        "--track", "t02",
        "--output", str(out),
        "--offline",
        "--seed", "42",
    ])

    assert result == 0
    audit_path = out / "audit_log.jsonl"
    events = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
    assert len(events) == 20
    assert all(event["action"] == "review:reject" for event in events)
    assert all(event["actor"] == "Nguyen Tuan Hung" for event in events)
    assert all(event["reason"] == "Manual review" for event in events)
    assert pd.read_csv(out / "ranked_review.csv").equals(predictions)
