"""PoC Pipeline for T02: Raw QC Triage (Group G63).

Advanced multi-feature defect triage engine combining:
1. Adaptive Camera & Illumination Sharpness Normalization (Blur)
2. Multi-scale & Local Grid Saturated Over-exposure Detection (Glare)
3. Light-condition Aware Under-exposure Detection (Dark)
4. 8x8 Boundary Gradient Ratio Analysis (JPEG Compression)
"""
from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd

from .common.context import RunContext
from .common.contact_sheet import render_contact_sheet
from .common.decision import Decision, write_decision
from .common.image_ops import laplacian_variance, load_rgb, to_gray
from .common.manifest import verify_manifest
from .common.review import load_review_decisions, make_review_queue, write_review_queue
from .metrics.tracks import get_track


# ---------------------------------------------------------------- 01 LOAD
def load(ctx: RunContext) -> dict:
    manifest_path = ctx.input_dir / "manifest.csv"
    if manifest_path.exists():
        problems = verify_manifest(manifest_path)
        if problems:
            ctx.audit.log(actor="poc_pipeline", action="provenance_issues", item_id=str(manifest_path), after=problems[:10])
            if ctx.config.get("strict_provenance", False):
                raise ValueError(f"Provenance check failed: {problems[:2]}")
                
    images_csv = ctx.input_dir / "images.csv"
    if not images_csv.exists():
        raise FileNotFoundError(f"Missing images.csv in {ctx.input_dir}")
        
    df_images = pd.read_csv(images_csv)
    return {"images": df_images}


# ---------------------------------------------------------------- 02 PROCESS
def _compute_jpeg_blockiness(gray: np.ndarray) -> float:
    """Measures 8x8 block boundary discontinuity with regularized denominator."""
    diff_x = np.abs(gray[:, 1:] - gray[:, :-1])
    diff_y = np.abs(gray[1:, :] - gray[:-1, :])
    mean_all = (diff_x.mean() + diff_y.mean()) / 2.0
    if mean_all < 0.5:  # Flat image, no compression artifacts possible
        return 0.0
    bx = diff_x[:, 7::8].mean() if diff_x.shape[1] > 8 else 0.0
    by = diff_y[7::8, :].mean() if diff_y.shape[0] > 8 else 0.0
    # Regularized denominator prevents division-by-near-zero explosion
    return float((bx + by) / 2.0 / (mean_all + 1.5))


def _compute_local_glare(gray: np.ndarray, grid_r: int = 6, grid_c: int = 6) -> float:
    """Detects localized washed-out regions using a fine 6x6 grid."""
    h, w = gray.shape
    r_step = h // grid_r
    c_step = w // grid_c
    max_sat = 0.0
    for r in range(grid_r):
        for c in range(grid_c):
            cell = gray[r * r_step:(r + 1) * r_step, c * c_step:(c + 1) * c_step]
            sat_frac = (cell > 240).mean()
            if sat_frac > max_sat:
                max_sat = float(sat_frac)
    return max_sat


def process(ctx: RunContext, data: dict) -> pd.DataFrame:
    df = data["images"].copy()
    
    scores = []
    pred_types = []
    reasons = []
    
    # Sharpness baseline thresholds per (camera, light) derived strictly on dev split
    sharpness_floors = {
        ("cam_A", "day"): 30.0,
        ("cam_A", "dusk"): 20.0,
        ("cam_A", "night"): 8.0,
        ("cam_B", "day"): 18.0,
        ("cam_B", "dusk"): 12.0,
        ("cam_B", "night"): 4.5,
    }
    
    for _, row in df.iterrows():
        img_path = ctx.input_dir / row["path"]
        img = load_rgb(img_path)
        gray = to_gray(img)
        
        cam = row.get("camera_id", "cam_A")
        light = row.get("light", "day")
        floor = sharpness_floors.get((cam, light), 15.0)
        
        # 1. Sharpness / Blur feature
        lap_var = laplacian_variance(img)
        blur_risk = max(0.0, (floor - lap_var) / floor) if lap_var < floor else 0.0
        
        # 2. Glare features (global + local grid)
        global_sat = float((gray > 245).mean())
        local_sat = _compute_local_glare(gray)
        glare_risk = max(global_sat * 2.5, local_sat * 1.5)
        
        # 3. Dark / Underexposure feature
        mean_lum = float(gray.mean())
        dark_frac = float((gray < 25).mean())
        if light == "night":
            dark_risk = 1.0 if (mean_lum < 8.0 and dark_frac > 0.88) else 0.0
        elif light == "dusk":
            dark_risk = max(0.0, (25.0 - mean_lum) / 25.0) if mean_lum < 25.0 else 0.0
        else:  # day
            dark_risk = max(0.0, (40.0 - mean_lum) / 40.0) if mean_lum < 40.0 else 0.0
            
        # 4. Compression blockiness feature
        blockiness = _compute_jpeg_blockiness(gray)
        comp_risk = max(0.0, (blockiness - 1.25) * 3.0) if blockiness > 1.25 else 0.0
        
        # Overall risk scoring & primary defect assignment
        risks = {
            "blur": blur_risk,
            "glare": glare_risk,
            "dark": dark_risk,
            "compression": comp_risk,
        }
        
        max_defect = max(risks, key=risks.get)
        max_risk = risks[max_defect]
        
        # Composite score: prioritizing highest risk factor + small secondary contributions
        total_score = max_risk * 100.0 + sum(risks.values()) * 5.0
        
        if max_risk < 0.15:
            pred_types.append("none")
            reasons.append("clean_sample")
        else:
            pred_types.append(max_defect)
            reasons.append(f"high_{max_defect}_risk")
            
        scores.append(round(total_score, 4))
        
    df["score"] = scores
    df["pred_defect_type"] = pred_types
    df["reason"] = reasons
    return df


# ---------------------------------------------------------------- 03 RANK
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
        title=f"T02 PoC Review Queue (Top-{budget})"
    )
    return q


# ---------------------------------------------------------------- 04 REVIEW
def review(ctx: RunContext, scored: pd.DataFrame, queue: pd.DataFrame) -> pd.DataFrame:
    reviewed_path = ctx.output_dir / "review_queue_reviewed.csv"
    if reviewed_path.exists():
        reviewed = load_review_decisions(reviewed_path)
        ctx.stats["n_reviewed"] = len(reviewed)
        # Apply reviewer overrides if present
        for _, r in reviewed.iterrows():
            item_id = r["item_id"]
            decision = r.get("reviewer_decision", "")
            override = r.get("override_value", "")
            if decision == "reject" or override == "none":
                scored.loc[scored["image_id"] == item_id, "score"] = 0.0
                scored.loc[scored["image_id"] == item_id, "pred_defect_type"] = "none"
            ctx.audit.log(actor=r.get("reviewer", "human"), action="override", item_id=str(item_id), after=decision)
    return scored


# ---------------------------------------------------------------- 05 DECIDE
def decide(ctx: RunContext, final: pd.DataFrame) -> Decision:
    # Production policy: If high defect density in batch, trigger REWORK; else GO with review log
    high_risk_count = (final["score"] > 30.0).sum()
    if high_risk_count > 35:
        status = "REWORK"
        reason_code = "HIGH_DEFECT_RATE"
        reason = f"High defect prevalence detected: {high_risk_count} images flagged"
    else:
        status = "GO"
        reason_code = "QUALITY_GATE_PASSED"
        reason = f"Triage complete: {high_risk_count} candidates prioritised for review queue"
        
    return Decision(
        status=status,
        reason_code=reason_code,
        reason=reason,
        owner=ctx.config.get("owner", "Dang Thu Thuy (Data Lead)"),
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
    
    out_cols = spec.pred_columns + [c for c in final.columns if c not in spec.pred_columns]
    final[out_cols].to_csv(ctx.out(spec.pred_file), index=False)
    
    decision = decide(ctx, final)
    write_decision(decision, ctx.out("decision.json"), ctx.out("decision_log.csv"))
