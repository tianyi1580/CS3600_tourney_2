from __future__ import annotations

import unittest

from Yolanda.strategy.adaptation import (
    BASE_A,
    BASE_C,
    BASE_D,
    BASE_F,
    D_CLAMP_MARGIN,
    ENV_A,
    ENV_C,
    ENV_D,
    ENV_F,
    RawDeltas,
    apply_adaptation,
    compute_confidence,
    pattern_raw_deltas,
)
from Yolanda.tracking.opponent_observation import OpponentCategory


class AdaptationClampTests(unittest.TestCase):
    """M3 adaptation: apply_adaptation + infer_opponent_category envelope contracts (bot_plan_v4)."""

    def test_confidence_below_floor_zeros_adaptation(self) -> None:
        raw = RawDeltas(da=1.0, dc=1.0, dd=1.0, df=1.0, d_margin=1.0)
        a, c, d, f, dm = apply_adaptation(0.34, raw)
        self.assertEqual(dm, 0.0)
        self.assertEqual(a, BASE_A)
        self.assertEqual(c, BASE_C)
        self.assertEqual(d, BASE_D)
        self.assertEqual(f, BASE_F)

    def test_effective_coefficients_stay_in_absolute_envelopes(self) -> None:
        raw = RawDeltas(da=1.0, dc=1.0, dd=1.0, df=1.0, d_margin=0.2)
        for conf in (0.35, 0.5, 1.0):
            a, c, d, f, dm = apply_adaptation(conf, raw)
            self.assertGreaterEqual(a, ENV_A[0])
            self.assertLessEqual(a, ENV_A[1])
            self.assertGreaterEqual(c, ENV_C[0])
            self.assertLessEqual(c, ENV_C[1])
            self.assertGreaterEqual(d, ENV_D[0])
            self.assertLessEqual(d, ENV_D[1])
            self.assertGreaterEqual(f, ENV_F[0])
            self.assertLessEqual(f, ENV_F[1])
            self.assertGreaterEqual(dm, D_CLAMP_MARGIN[0])
            self.assertLessEqual(dm, D_CLAMP_MARGIN[1])

    def test_pattern_raw_deltas_aggregate_table_rows(self) -> None:
        hist = {
            OpponentCategory.PLAIN: 2,
            OpponentCategory.PRIME: 10,
            OpponentCategory.CARPET: 2,
            OpponentCategory.SEARCH: 10,
        }
        raw = pattern_raw_deltas(
            category_hist=hist,
            total_typed=24,
            mean_opp_mobility=2.0,
            low_exit_rate=0.5,
            search_attempts=10,
            search_correct=1,
        )
        self.assertGreater(raw.df, 0.0)
        self.assertGreater(raw.dd, 0.0)
        self.assertLess(raw.d_margin, 0.0)

    def test_compute_confidence_bounded(self) -> None:
        c0 = compute_confidence(6, 0.0)
        self.assertGreaterEqual(c0, 0.0)
        self.assertLessEqual(c0, 1.0)
        c1 = compute_confidence(100, 1.0)
        self.assertEqual(c1, 0.0)

    def test_margin_delta_requires_min_non_search_observations(self) -> None:
        hist = {
            OpponentCategory.PLAIN: 0,
            OpponentCategory.PRIME: 0,
            OpponentCategory.CARPET: 0,
            OpponentCategory.SEARCH: 24,
        }
        raw = pattern_raw_deltas(
            category_hist=hist,
            total_typed=24,
            mean_opp_mobility=3.0,
            low_exit_rate=0.1,
            search_attempts=12,
            search_correct=1,
        )
        self.assertEqual(raw.d_margin, 0.0)


if __name__ == "__main__":
    unittest.main()
