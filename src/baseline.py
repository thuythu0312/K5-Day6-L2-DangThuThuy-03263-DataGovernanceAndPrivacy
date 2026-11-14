"""Baseline Pipeline for T02: Raw QC Triage.

Uses a single global Laplacian variance threshold to rank defect candidates.
Serves as the benchmark (bar to beat) for the improved PoC.
"""
from __future__ import annotations

from pathlib import Path
import pandas as pd

from .common.context import RunContext
from .common.contact_sheet import render_contact_sheet
from .common.decision import Decision, write_decision
from .common.image_ops import laplacian_variance, load_rgb
from .common.manifest import verify_manifest
from .common.review import make_review_queue, write_review_queue
from .metrics.tracks import get_track


def load(ctx: RunContext) -> dict:
    manifest_path = ctx.input_dir / "manifest.csv"
    if manifest_path.exists():
        problems = verify_manifest(manifest_path)
        if problems:
            ctx.audit.log(actor="baseline", action="provenance_issues", item_id=str(manifest_path), after=problems[:10])
    
    images_csv = ctx.input_dir / "images.csv"
    if not images_csv.exists():
        raise FileNotFoundError(f"Missing images.csv in {ctx.input_dir}")
    
    df_images = pd.read_csv(images_csv)
    return {"images": df_images}


def process(ctx: RunContext, data: dict) -> pd.DataFrame:
    df = data["images"].copy()
    scores = []
    
    for _, row in df.iterrows():
        img_path = ctx.input_dir / row["path"]
        img = load_rgb(img_path)
        var = laplacian_variance(img)
        # Low sharpness -> high risk score
        score = round(1000.0 / (var + 1.0), 4)
        scores.append(score)
        
    df["score"] = scores
    df["pred_defect_type"] = "blur"
    df["reason"] = "low_sharpness_baseline"
    return df


def rank(ctx: RunContext, scored: pd.DataFrame) -> pd.DataFrame:
    budget = int(ctx.param("budget", 20))
    q = make_review_queue(
        scored,
        id_col="image_id",
        score_col="score",
        budget=budget,
        reason_col="reason",
        evidence_col="path"
    )
    write_review_queue(q, ctx.out("review_queue.csv"))
    render_contact_sheet(
        q,
        ctx.out("contact_sheet.html"),
        image_root=ctx.input_dir,
        title=f"T02 Baseline Review Queue (Top-{budget})"
    )
    return q


def review(ctx: RunContext, scored: pd.DataFrame, queue: pd.DataFrame) -> pd.DataFrame:
    # Baseline pass-through without reviewer overrides
    return scored


def decide(ctx: RunContext, final: pd.DataFrame) -> Decision:
    return Decision(
        status="HOLD",
        reason_code="BASELINE_ONLY",
        reason="Baseline run with single global Laplacian variance: insufficient for release gate",
        owner=ctx.config.get("owner", "Dang Thu Thuy"),
        scope=ctx.track,
        evidence=[str(ctx.out("ranked_review.csv"))]
    )


def run(ctx: RunContext) -> None:
    spec = get_track(ctx.track)
    data = load(ctx)
    scored = process(ctx, data)
    ctx.stats["n_items"] = len(scored)
    queue = rank(ctx, scored)
    final = review(ctx, scored, queue)
    
    # Save required output
    out_cols = spec.pred_columns + [c for c in final.columns if c not in spec.pred_columns]
    final[out_cols].to_csv(ctx.out(spec.pred_file), index=False)
    
    # Save decision
    write_decision(decide(ctx, final), ctx.out("decision.json"), ctx.out("decision_log.csv"))
