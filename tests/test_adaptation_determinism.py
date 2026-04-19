from __future__ import annotations

import unittest

from Yolanda.strategy.adaptation import RawDeltas, apply_adaptation, compute_confidence, pattern_raw_deltas
from Yolanda.tracking.opponent_observation import OpponentCategory


class AdaptationDeterminismTests(unittest.TestCase):
    """M3: identical profile inputs yield identical effective_a and adaptive_margin_delta."""

    def test_repeated_apply_adaptation_identical(self) -> None:
        hist = {
            OpponentCategory.PLAIN: 4,
            OpponentCategory.PRIME: 8,
            OpponentCategory.CARPET: 4,
            OpponentCategory.SEARCH: 8,
        }
        raw = pattern_raw_deltas(
            category_hist=hist,
            total_typed=24,
            mean_opp_mobility=2.0,
            low_exit_rate=0.45,
            search_attempts=8,
            search_correct=1,
        )
        conf = compute_confidence(20, 0.5)
        bases = (0.95, 0.55, 0.4, 0.72)
        out1 = apply_adaptation(conf, raw, base_a=bases[0], base_c=bases[1], base_d=bases[2], base_f=bases[3])
        out2 = apply_adaptation(conf, raw, base_a=bases[0], base_c=bases[1], base_d=bases[2], base_f=bases[3])
        self.assertEqual(out1, out2)

    def test_zero_raw_deltas_preserve_bases(self) -> None:
        raw = RawDeltas()
        a, c, d, f, dm = apply_adaptation(1.0, raw, base_a=1.0, base_c=0.6, base_d=0.35, base_f=0.75)
        self.assertEqual(dm, 0.0)
        self.assertAlmostEqual(a, 1.0, places=6)
        self.assertAlmostEqual(c, 0.6, places=6)
        self.assertAlmostEqual(d, 0.35, places=6)
        self.assertAlmostEqual(f, 0.75, places=6)


if __name__ == "__main__":
    unittest.main()
