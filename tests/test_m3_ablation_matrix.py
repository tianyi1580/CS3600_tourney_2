from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "workflows" / "m3_ablation_matrix.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("m3_ablation_matrix", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load workflows/m3_ablation_matrix.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class M3AblationMatrixTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = _load_module()

    def test_parse_metric_extracts_mean_delta(self) -> None:
        text = "Mean score delta (M3 - M2 baseline)=-4.550"
        value = self.module.parse_metric(text, self.module.RE_MEAN_DELTA, "mean delta")
        self.assertEqual(value, "-4.550")

    def test_parse_metric_raises_for_missing_metric(self) -> None:
        with self.assertRaises(RuntimeError):
            self.module.parse_metric("no metric", self.module.RE_ELO_DELTA, "elo")

    def test_enforcement_fails_when_full_m3_is_not_absolutely_viable(self) -> None:
        cfg = self.module.AblationConfig
        res = self.module.AblationResult
        results = [
            res(cfg("full_m3", True, True), mean_delta=-0.1, elo_delta=1.0, search_precision=0.3, promotion_gate="PASS", raw_output=""),
            res(cfg("no_model_no_margin", False, False), mean_delta=-0.2, elo_delta=-1.0, search_precision=0.3, promotion_gate="FAIL", raw_output=""),
        ]
        failures = self.module.evaluate_ablation_enforcement(results)
        self.assertTrue(any("full_m3_mean_delta" in f for f in failures))

    def test_enforcement_fails_when_full_m3_gate_is_fail(self) -> None:
        cfg = self.module.AblationConfig
        res = self.module.AblationResult
        results = [
            res(cfg("full_m3", True, True), mean_delta=0.2, elo_delta=2.0, search_precision=0.3, promotion_gate="FAIL", raw_output=""),
            res(cfg("no_model_no_margin", False, False), mean_delta=0.1, elo_delta=1.0, search_precision=0.3, promotion_gate="PASS", raw_output=""),
        ]
        failures = self.module.evaluate_ablation_enforcement(results)
        self.assertTrue(any("full_m3_gate" in f for f in failures))

    def test_enforcement_fails_when_full_m3_elo_nonpositive_even_if_mean_positive(self) -> None:
        cfg = self.module.AblationConfig
        res = self.module.AblationResult
        results = [
            res(cfg("full_m3", True, True), mean_delta=0.2, elo_delta=0.0, search_precision=0.3, promotion_gate="PASS", raw_output=""),
            res(cfg("no_adaptive_margin", True, False), mean_delta=0.1, elo_delta=-0.5, search_precision=0.3, promotion_gate="FAIL", raw_output=""),
            res(cfg("no_opponent_model", False, True), mean_delta=0.05, elo_delta=-1.0, search_precision=0.3, promotion_gate="FAIL", raw_output=""),
            res(cfg("no_model_no_margin", False, False), mean_delta=-0.1, elo_delta=-2.0, search_precision=0.3, promotion_gate="FAIL", raw_output=""),
        ]
        failures = self.module.evaluate_ablation_enforcement(results)
        self.assertTrue(any("full_m3_elo_delta" in f for f in failures))

    def test_enforcement_fails_when_all_configs_lose_absolute_criteria(self) -> None:
        """Relative 'best among ablations' must not greenlight full M3 when it is not viable."""
        cfg = self.module.AblationConfig
        res = self.module.AblationResult
        results = [
            res(cfg("full_m3", True, True), mean_delta=-0.05, elo_delta=-1.0, search_precision=0.3, promotion_gate="FAIL", raw_output=""),
            res(cfg("no_adaptive_margin", True, False), mean_delta=-0.15, elo_delta=-1.5, search_precision=0.3, promotion_gate="FAIL", raw_output=""),
            res(cfg("no_opponent_model", False, True), mean_delta=-0.12, elo_delta=-1.2, search_precision=0.3, promotion_gate="FAIL", raw_output=""),
            res(cfg("no_model_no_margin", False, False), mean_delta=-0.20, elo_delta=-2.0, search_precision=0.3, promotion_gate="FAIL", raw_output=""),
        ]
        failures = self.module.evaluate_ablation_enforcement(results)
        self.assertTrue(any("full_m3_mean_delta" in f for f in failures))
        self.assertTrue(any("full_m3_elo_delta" in f for f in failures))
        self.assertTrue(any("full_m3_gate" in f for f in failures))

    def test_enforcement_fails_when_simpler_config_beats_full_on_mean_delta(self) -> None:
        cfg = self.module.AblationConfig
        res = self.module.AblationResult
        results = [
            res(cfg("full_m3", True, True), mean_delta=0.2, elo_delta=3.0, search_precision=0.3, promotion_gate="PASS", raw_output=""),
            res(cfg("no_adaptive_margin", True, False), mean_delta=0.35, elo_delta=2.0, search_precision=0.3, promotion_gate="PASS", raw_output=""),
            res(cfg("no_opponent_model", False, True), mean_delta=0.1, elo_delta=1.0, search_precision=0.3, promotion_gate="PASS", raw_output=""),
            res(cfg("no_model_no_margin", False, False), mean_delta=-0.1, elo_delta=0.0, search_precision=0.3, promotion_gate="FAIL", raw_output=""),
        ]
        failures = self.module.evaluate_ablation_enforcement(results)
        self.assertTrue(any("best_ablation(no_adaptive_margin)" in f for f in failures))

    def test_enforcement_passes_when_full_m3_positive_and_not_outperformed(self) -> None:
        cfg = self.module.AblationConfig
        res = self.module.AblationResult
        results = [
            res(cfg("full_m3", True, True), mean_delta=0.4, elo_delta=5.0, search_precision=0.3, promotion_gate="PASS", raw_output=""),
            res(cfg("no_adaptive_margin", True, False), mean_delta=0.2, elo_delta=2.0, search_precision=0.3, promotion_gate="PASS", raw_output=""),
            res(cfg("no_opponent_model", False, True), mean_delta=0.1, elo_delta=1.0, search_precision=0.3, promotion_gate="PASS", raw_output=""),
        ]
        failures = self.module.evaluate_ablation_enforcement(results)
        self.assertEqual(failures, [])


if __name__ == "__main__":
    unittest.main()
