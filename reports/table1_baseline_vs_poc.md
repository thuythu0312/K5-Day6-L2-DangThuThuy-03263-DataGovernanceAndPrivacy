Baseline: `baseline` (git b0ce8bf, seed 42) · PoC: `poc` (git b0ce8bf, seed 42)

| Metric (unit) | Slice | Baseline | PoC | Δ abs | Δ rel | Better | N |
|---|---|---|---|---|---|---|---|
| **Defect Recall@B** (GT defects in top-B / GT defects) | all | 0.3810 | 0.4762 | 0.0952 | +25.0% | higher | 56 |
| Precision@B (GT defects in top-B / B) | all | 0.8000 | 1.0000 | 0.2000 | +25.0% | higher | 56 |
| Defect-type accuracy (GT defects) (fraction) | all | 0.5714 | 0.5952 | 0.0238 | +4.2% | higher | 42 |
| False alarm in top-B (clean images in top-B / clean images) | light=day | 0.3333 | 0.0000 | -0.3333 | -100.0% | lower | 36 |
| False alarm in top-B (clean images in top-B / clean images) | light=dusk | 0.2500 | 0.0000 | -0.2500 | -100.0% | lower | 16 |
| False alarm in top-B (clean images in top-B / clean images) | light=night | 0.0000 | 0.0000 | 0.0000 | baseline=0 | lower | 4 |
| Runtime / 100 items (s) | all | 0.2919 | 0.3678 | | | lower | |
