from __future__ import annotations

import unittest

import numpy as np

from common import identity_transition, make_board, random_stochastic_transition
from game.enums import Noise
from Yolanda.tracking.belief import BeliefEngine


class BeliefEngineTests(unittest.TestCase):
    def test_predict_update_is_normalized(self) -> None:
        board = make_board()
        belief = BeliefEngine(identity_transition())

        belief.predict(use_single_step=False, opp_miss_cell=None)
        posterior = belief.update(Noise.SQUEAK, 4, board)

        self.assertAlmostEqual(float(np.sum(posterior)), 1.0, places=6)
        self.assertTrue(np.all(posterior >= 0.0))

    def test_reset_after_capture_matches_cached_prior(self) -> None:
        belief = BeliefEngine(identity_transition())
        belief.belief = np.full(64, 1.0 / 64.0, dtype=np.float64)

        reset = belief.reset_after_capture()
        self.assertTrue(np.allclose(reset, belief.reset_prior))
        self.assertAlmostEqual(float(np.sum(reset)), 1.0, places=6)

    def test_false_search_feedback_zeroes_location(self) -> None:
        belief = BeliefEngine(identity_transition())
        belief.belief = np.full(64, 1.0 / 64.0, dtype=np.float64)

        belief.apply_search_feedback((0, 0), False)
        self.assertAlmostEqual(belief.probability_at((0, 0)), 0.0, places=8)
        self.assertAlmostEqual(float(np.sum(belief.belief)), 1.0, places=6)

    def test_reset_prior_parity_non_identity_transition(self) -> None:
        """belief reset parity: cached respawn prior matches e_0 @ T^1000 (assignment §10.4)."""
        rng = np.random.default_rng(12345)
        for _ in range(3):
            raw_t = random_stochastic_transition(rng)
            belief = BeliefEngine(raw_t)
            t = belief.transition_matrix
            e0 = np.zeros(64, dtype=np.float64)
            e0[0] = 1.0
            expected = e0 @ np.linalg.matrix_power(t, 1000)
            self.assertTrue(np.allclose(belief.reset_prior, expected, rtol=1e-9, atol=1e-9))
            self.assertAlmostEqual(float(np.sum(belief.reset_prior)), 1.0, places=8)

    def test_true_search_feedback_matches_reset_prior(self) -> None:
        belief = BeliefEngine(random_stochastic_transition(np.random.default_rng(99)))
        belief.belief = np.full(64, 1.0 / 64.0, dtype=np.float64)
        out = belief.apply_search_feedback((5, 3), True)
        self.assertTrue(np.allclose(out, belief.reset_prior))
        self.assertTrue(np.allclose(belief.belief, belief.reset_prior))

    def test_long_predict_update_chain_stable_normalized(self) -> None:
        board = make_board()
        belief = BeliefEngine(random_stochastic_transition(np.random.default_rng(7)))
        for _ in range(80):
            belief.predict(use_single_step=False, opp_miss_cell=None)
            self.assertAlmostEqual(float(np.sum(belief.belief)), 1.0, places=5)
            self.assertTrue(np.all(belief.belief >= -1e-12))
            belief.update(Noise.SCRATCH, 3, board)
            self.assertAlmostEqual(float(np.sum(belief.belief)), 1.0, places=5)


if __name__ == "__main__":
    unittest.main()
