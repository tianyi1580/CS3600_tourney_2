from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "workflows" / "m3_competitive_batch.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("m3_competitive_batch", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load workflows/m3_competitive_batch.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class M3CompetitiveBatchGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = _load_module()

    def test_gate_passes_when_metrics_and_reliability_are_clean(self) -> None:
        gate_pass, failures = self.module.evaluate_promotion_gate(
            sample_count=80,
            min_games_for_gate=80,
            mean_delta=1.5,
            elo_delta=12.0,
            reliability_timeouts=0,
            reliability_invalid=0,
            reliability_crashes=0,
            m3_timeout_losses=0,
        )
        self.assertTrue(gate_pass)
        self.assertEqual(failures, [])

    def test_gate_fails_on_negative_score_delta(self) -> None:
        gate_pass, failures = self.module.evaluate_promotion_gate(
            sample_count=80,
            min_games_for_gate=80,
            mean_delta=-0.1,
            elo_delta=5.0,
            reliability_timeouts=0,
            reliability_invalid=0,
            reliability_crashes=0,
            m3_timeout_losses=0,
        )
        self.assertFalse(gate_pass)
        self.assertTrue(any("mean_score_delta" in msg for msg in failures))

    def test_gate_fails_on_negative_elo_delta(self) -> None:
        gate_pass, failures = self.module.evaluate_promotion_gate(
            sample_count=80,
            min_games_for_gate=80,
            mean_delta=0.1,
            elo_delta=-0.1,
            reliability_timeouts=0,
            reliability_invalid=0,
            reliability_crashes=0,
            m3_timeout_losses=0,
        )
        self.assertFalse(gate_pass)
        self.assertTrue(any("elo_delta_vs_start" in msg for msg in failures))

    def test_gate_fails_on_reliability_regressions(self) -> None:
        gate_pass, failures = self.module.evaluate_promotion_gate(
            sample_count=80,
            min_games_for_gate=80,
            mean_delta=0.5,
            elo_delta=1.0,
            reliability_timeouts=1,
            reliability_invalid=0,
            reliability_crashes=0,
            m3_timeout_losses=0,
        )
        self.assertFalse(gate_pass)
        self.assertTrue(any("reliability_regression" in msg for msg in failures))

    def test_gate_fails_when_sample_count_is_too_small(self) -> None:
        gate_pass, failures = self.module.evaluate_promotion_gate(
            sample_count=20,
            min_games_for_gate=80,
            mean_delta=2.0,
            elo_delta=20.0,
            reliability_timeouts=0,
            reliability_invalid=0,
            reliability_crashes=0,
            m3_timeout_losses=0,
        )
        self.assertFalse(gate_pass)
        self.assertTrue(any("insufficient_sample_count" in msg for msg in failures))


if __name__ == "__main__":
    unittest.main()
