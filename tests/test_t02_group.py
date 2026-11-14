"""Unit tests for Group G63 - Track T02 (Raw QC Triage).

Tests verify:
1. End-to-end pipeline execution & output schema contract
2. Failure mode 1: Avoiding false alarms on valid night scenes
3. Failure mode 2: Reliable detection of localized glare (e.g. overexposed plate)
"""
import unittest
from pathlib import Path
import numpy as np
import pandas as pd

from src.common.context import RunContext
from src.common.image_ops import to_gray
from src.pipeline import _compute_local_glare, _compute_jpeg_blockiness, process, decide


class TestT02Group63(unittest.TestCase):

    def test_pipeline_e2e_contract(self):
        """Verify process() outputs required schema and valid scores."""
        ctx = RunContext(
            track="t02",
            input_dir=Path("fixtures/t02_raw_qc"),
            output_dir=Path("out/poc"),
            config={"owner": "Dang Thu Thuy (Data Lead)"},
            seed=42,
            rng=np.random.default_rng(42)
        )
        images_df = pd.read_csv("fixtures/t02_raw_qc/images.csv").head(8)
        scored = process(ctx, {"images": images_df})
        
        # Verify required columns
        self.assertIn("image_id", scored.columns)
        self.assertIn("score", scored.columns)
        self.assertIn("pred_defect_type", scored.columns)
        
        # Verify score integrity
        self.assertEqual(len(scored), 8)
        self.assertTrue((scored["score"] >= 0.0).all())
        
        # Verify decision policy contract
        decision = decide(ctx, scored)
        self.assertIn(decision.status, ["GO", "HOLD", "REWORK"])
        self.assertTrue(len(decision.reason_code) > 0)
        self.assertEqual(decision.owner, "Dang Thu Thuy (Data Lead)")

    def test_failure_mode_night_scene_no_false_alarm(self):
        """Failure mode 1: Sharp night scenes must not trigger false blur alarms."""
        # Clean synthetic dark frame with a clear edge (e.g. street light / vehicle outline)
        clean_night = np.full((180, 320, 3), 15, dtype=np.uint8)
        clean_night[80:100, 140:180] = 180  # clear high-contrast feature
        
        gray = to_gray(clean_night)
        # Verify it is not falsely tagged as severe glare, dark, or compression
        glare = _compute_local_glare(gray)
        block = _compute_jpeg_blockiness(gray)
        
        self.assertLess(glare, 0.20, "Clean night scene should not trigger glare defect")
        self.assertLess(block, 1.25, "Uncompressed night frame should not trigger blockiness defect")

    def test_failure_mode_local_plate_glare_detected(self):
        """Failure mode 2: Localized plate washout must be flagged by local grid glare detector."""
        # Overall dark/normal image with a 20x40 washed-out license plate region (pixels > 245)
        scene = np.full((180, 320, 3), 60, dtype=np.uint8)
        scene[120:145, 140:190] = 255  # washed-out license plate
        
        gray = to_gray(scene)
        local_glare = _compute_local_glare(gray)
        
        # Must detect high local saturation even though global saturation is tiny (< 3%)
        global_sat = (gray > 245).mean()
        self.assertLess(global_sat, 0.05, "Global saturation is low")
        self.assertGreater(local_glare, 0.10, "Local grid detector must catch localized glare")


if __name__ == "__main__":
    unittest.main()
