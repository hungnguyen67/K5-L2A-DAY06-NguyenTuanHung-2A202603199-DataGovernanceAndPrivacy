"""YOUR PoC PIPELINE — this is the file your group owns.

Lab contract = 5 automated steps, run by `python -m src.main ...`:
    01 load      input + provenance check (manifest.csv)
    02 process   your algorithm / model (the research part)
    03 rank      prioritise for a fixed review budget B
    04 review    human-in-the-loop: queue -> reviewer decisions -> overrides + audit log
    05 decide    GO / HOLD / REWORK (or track equivalent) with reason_code + owner, write outputs

Required output: out/<pred_file> with the columns listed for your track in
docs/tracks/TXX.md (also in src/metrics/tracks.py::TRACKS). Then evaluate with
    python -m src.evaluate --track tXX --pred out/<pred_file>

Rules: never read fixtures/*/gt/ here (the GT guard will stop you); seed everything via ctx.rng;
no network calls; fail loudly on missing models instead of downloading.
See src/examples/random_baseline.py for a minimal end-to-end wiring example.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .common.contact_sheet import render_contact_sheet
from .common.context import RunContext
from .common.decision import Decision, write_decision
from .common.image_ops import brightness_stats, laplacian_variance, load_rgb
from .common.manifest import verify_manifest
from .common.review import load_review_decisions, make_review_queue, write_review_queue
from .metrics.tracks import get_track


# ---------------------------------------------------------------- 01 load
def load(ctx: RunContext) -> dict:
    manifest = ctx.input_dir / "manifest.csv"
    problems = verify_manifest(manifest) if manifest.exists() else [{"problem": "no_manifest"}]
    if problems:
        ctx.audit.log(actor="pipeline", action="provenance_problems", item_id=str(manifest), after=problems[:20])
        if ctx.config.get("strict_provenance", True):
            raise ValueError(f"provenance check failed ({len(problems)} problems), first: {problems[:3]}")
    data = {"manifest": pd.read_csv(manifest) if manifest.exists() else None}
    if ctx.track == "t02":
        images_path = ctx.input_dir / "images.csv"
        images = pd.read_csv(images_path)
        required = {"image_id", "path", "camera_id", "light", "split"}
        missing = sorted(required - set(images.columns))
        if missing:
            raise ValueError(f"{images_path} missing required columns: {missing}")
        if images["image_id"].isna().any() or images["image_id"].duplicated().any():
            raise ValueError(f"{images_path} must contain unique, non-empty image_id values")
        if images[list(required)].isna().any().any():
            raise ValueError(f"{images_path} contains empty required values")
        data["images"] = images
    return data


# ---------------------------------------------------------------- 02 process
def process(ctx: RunContext, data: dict) -> pd.DataFrame:
    if ctx.track != "t02":
        spec = get_track(ctx.track)
        raise NotImplementedError(
            f"Implement process() for {spec.track} ({spec.title}). It must produce a DataFrame with at least "
            f"{spec.pred_columns} (saved as out/{spec.pred_file}). See docs/tracks/{spec.track.upper()}.md"
        )

    images = data.get("images")
    if not isinstance(images, pd.DataFrame) or images.empty:
        raise ValueError("T02 requires a non-empty images.csv table")

    rows = []
    for row in images.itertuples(index=False):
        image_path = ctx.input_dir / str(row.path)
        if not image_path.is_file():
            raise FileNotFoundError(f"T02 image not found: {image_path}")
        image = load_rgb(image_path)
        brightness = brightness_stats(image)
        rows.append(
            {
                "image_id": str(row.image_id),
                "path": str(row.path),
                "camera_id": str(row.camera_id),
                "light": str(row.light),
                "split": str(row.split),
                "log_sharpness": float(np.log1p(laplacian_variance(image))),
                "mean_brightness": brightness["mean"],
                "frac_dark": brightness["frac_dark"],
                "frac_saturated": brightness["frac_saturated"],
            }
        )
    scored = pd.DataFrame(rows)

    dev_split = str(ctx.param("dev_split", "dev"))
    dev = scored[scored["split"] == dev_split]
    if dev.empty:
        raise ValueError(f"T02 has no rows in configured dev split {dev_split!r}")

    feature_names = ("log_sharpness", "mean_brightness", "frac_dark", "frac_saturated")

    def location_scale(values: pd.Series) -> tuple[float, float]:
        array = values.to_numpy(dtype=float)
        median = float(np.median(array))
        scale = float(1.4826 * np.median(np.abs(array - median)))
        if scale <= 1e-6:
            q25, q75 = np.percentile(array, [25, 75])
            scale = float((q75 - q25) / 1.349)
        if scale <= 1e-6:
            scale = float(np.std(array))
        return median, max(scale, 1e-6)

    global_reference = {name: location_scale(dev[name]) for name in feature_names}
    group_reference = {}
    for key, group in dev.groupby(["camera_id", "light"], sort=False):
        if len(group) >= 3:
            group_reference[key] = {name: location_scale(group[name]) for name in feature_names}

    scores = []
    reasons = []
    for row in scored.itertuples(index=False):
        reference = group_reference.get((row.camera_id, row.light), global_reference)

        def anomaly(feature: str, direction: float) -> float:
            center, scale = reference[feature]
            value = getattr(row, feature)
            return float(np.clip(direction * (value - center) / scale, 0.0, 4.0))

        signals = {
            "blur": anomaly("log_sharpness", -1.0),
            "dark": max(
                anomaly("mean_brightness", -1.0),
                anomaly("frac_dark", 1.0),
            ),
            "glare": anomaly("frac_saturated", 1.0),
        }
        active = [name for name, value in signals.items() if value > 0]
        scores.append(sum(signals.values()))
        reasons.append("|".join(active) if active else "no_large_feature_deviation")

    scored["score"] = scores
    scored["reason"] = reasons
    return scored


# ---------------------------------------------------------------- 03 rank
def rank(ctx: RunContext, scored: pd.DataFrame) -> pd.DataFrame:
    """Default: top-B by `score`. Adapt id/score/reason columns to your track."""
    budget = int(ctx.param("budget", 20))
    if "score" not in scored.columns:
        raise ValueError("rank(): process() output needs a numeric `score` column (higher = review first), "
                         "or adapt rank() to your track")
    q = make_review_queue(scored, id_col=scored.columns[0], score_col="score", budget=budget,
                          reason_col="reason" if "reason" in scored.columns else None,
                          slice_col="light" if "light" in scored.columns else None,
                          evidence_col="path" if "path" in scored.columns else None)
    write_review_queue(q, ctx.out("review_queue.csv"))
    if ctx.track == "t02":
        render_contact_sheet(q, ctx.out("contact_sheet.html"), image_root=ctx.input_dir,
                             title="T02 Raw QC review queue")
    return q


# ---------------------------------------------------------------- 04 review
def review(ctx: RunContext, scored: pd.DataFrame, queue: pd.DataFrame) -> pd.DataFrame:
    """Audit reviewed decisions; T02 does not yet translate them into score overrides."""
    reviewed_path = ctx.output_dir / "review_queue_reviewed.csv"
    if reviewed_path.exists():
        reviewed = load_review_decisions(reviewed_path)
        ctx.stats["n_reviewed"] = len(reviewed)
        if len(reviewed):
            audit = ctx.audit
            if audit is None:
                raise RuntimeError("review decisions were provided but no audit log is configured")
            for row in reviewed.itertuples(index=False):
                audit.log(
                    actor=row.reviewer,
                    action=f"review:{row.reviewer_decision}",
                    item_id=row.item_id,
                    after={
                        "reviewer_decision": row.reviewer_decision,
                        "override_value": row.override_value,
                    },
                    reason=row.review_note,
                    track=ctx.track,
                    run_name=ctx.run_name,
                    reviewed_at=row.reviewed_at,
                )
    return scored


# ---------------------------------------------------------------- 05 decide
def decide(ctx: RunContext, final: pd.DataFrame) -> Decision:
    # TODO: replace with your policy (thresholds frozen BEFORE looking at eval results)
    return Decision(status="HOLD", reason_code="POLICY_NOT_IMPLEMENTED", reason="Decision policy not implemented yet",
                    owner=ctx.config.get("owner", "TODO-owner"), scope=ctx.track)


def run(ctx: RunContext) -> None:
    spec = get_track(ctx.track)
    data = load(ctx)
    scored = process(ctx, data)
    ctx.stats["n_items"] = len(scored)
    queue = rank(ctx, scored)
    final = review(ctx, scored, queue)
    final[spec.pred_columns + [c for c in final.columns if c not in spec.pred_columns]].to_csv(ctx.out(spec.pred_file), index=False)
    write_decision(decide(ctx, final), ctx.out("decision.json"), ctx.out("decision_log.csv"))
