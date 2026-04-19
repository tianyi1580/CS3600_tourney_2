from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from common import identity_transition, make_board
from yolanda_prime_v1_2.agent import PlayerAgent as LiveAgent
from yolanda_prime_v1_2.infra.time_manager import TimeManager
from yolanda_prime_v1_2_baseline.agent import PlayerAgent as BaselineAgent
from workflows.yp12_hyperopt import HYPEROPT_LADDER, InfrastructureFailure, definitive_improvement_check


class YP12HyperoptTests(unittest.TestCase):
    def test_hyperopt_ladder_contains_required_opponents_and_small_random_weight(self) -> None:
        names = [opponent.name for opponent in HYPEROPT_LADDER]
        self.assertIn("yolanda_prime_v1_2_baseline", names)
        self.assertIn("Yolanda3_3", names)
        self.assertIn("Yolanda5", names)
        self.assertIn("RandomSearchBaseline", names)

        total_weight = sum(opponent.weight for opponent in HYPEROPT_LADDER)
        random_weight = next(opponent.weight for opponent in HYPEROPT_LADDER if opponent.name == "RandomSearchBaseline")
        self.assertAlmostEqual(total_weight, 1.0)
        self.assertLess(random_weight, 0.10)

    def test_live_and_baseline_agents_use_separate_weight_channels(self) -> None:
        board = make_board(time_to_play=240)
        env = {
            "YP12_WEIGHTS_JSON": json.dumps({"a": 2.1, "time_opening_cap": 4.0}),
            "YP12_BASELINE_WEIGHTS_JSON": json.dumps({"a": 0.9, "time_opening_cap": 2.0}),
        }
        with patch.dict("os.environ", env, clear=False):
            live_agent = LiveAgent(board, identity_transition(), time_left=lambda: 10.0)
            baseline_agent = BaselineAgent(board, identity_transition(), time_left=lambda: 10.0)

        self.assertAlmostEqual(live_agent.policy_engine.a, 2.1)
        self.assertAlmostEqual(baseline_agent.policy_engine.a, 0.9)
        self.assertAlmostEqual(TimeManager.phase_cap(0, live_agent.runtime_state), 4.0)
        self.assertAlmostEqual(TimeManager.phase_cap(0, baseline_agent.runtime_state), 2.0)

    def test_definitive_check_fail_soft_on_infrastructure_failure(self) -> None:
        with patch("workflows.yp12_hyperopt.evaluate_series", side_effect=InfrastructureFailure("boom")):
            passed, details = definitive_improvement_check({"a": 1.4}, games_per_opponent=4)

        self.assertFalse(passed)
        self.assertEqual(len(details["rows"]), 4)
        self.assertTrue(all(row.get("infrastructure_failure") for row in details["rows"]))


if __name__ == "__main__":
    unittest.main()
