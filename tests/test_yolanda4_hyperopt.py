from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from common import identity_transition, make_board
from game.enums import ResultArbiter, WinReason
from Yolanda4.agent import PlayerAgent as LiveAgent
from Yolanda4.infra.time_manager import TimeManager
from Yolanda4.infra.weights import DEFAULTS, load_weights, parameter_names, vector_to_weights, weights_to_vector
from Yolanda4Baseline.agent import PlayerAgent as BaselineAgent
from workflows.y4_hyperopt import DEFAULT_LADDER, GameTask, InfrastructureFailure, SMOKE_LADDER, run_single_game


class Yolanda4HyperoptTests(unittest.TestCase):
    def test_parameter_profile_dimensions_match_design(self) -> None:
        self.assertEqual(len(parameter_names("tier_ab")), 13)
        self.assertEqual(len(parameter_names("documented_full")), 36)
        self.assertEqual(len(parameter_names("extended_full")), 42)

    def test_default_and_smoke_ladders_include_mitch12_and_sum_to_one(self) -> None:
        for ladder in (DEFAULT_LADDER, SMOKE_LADDER):
            self.assertIn("yolanda_mitch1_2", [opponent.name for opponent in ladder])
            self.assertAlmostEqual(sum(opponent.weight for opponent in ladder), 1.0)

    def test_load_weights_env_overrides_and_clamps(self) -> None:
        with patch.dict(
            "os.environ",
            {"Y4_WEIGHTS_JSON": json.dumps({"a": 9.0, "farmable_margin_base": -2.0})},
            clear=False,
        ):
            loaded = load_weights()
        self.assertEqual(loaded["a"], 3.0)
        self.assertEqual(loaded["farmable_margin_base"], 0.0)

    def test_load_weights_file_fallback_works(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            weights_path = Path(tmpdir) / "weights.json"
            weights_path.write_text(json.dumps({"a": 2.25, "time_opening_cap": 5.5}), encoding="utf-8")
            loaded = load_weights(package_root=Path(tmpdir), env_var="Y4_TEST_WEIGHTS_JSON")
        self.assertEqual(loaded["a"], 2.25)
        self.assertEqual(loaded["time_opening_cap"], 5.5)

    def test_vector_roundtrip_preserves_named_values(self) -> None:
        base_vector = weights_to_vector(DEFAULTS, profile="tier_ab")
        roundtrip = vector_to_weights(base_vector, profile="tier_ab")
        self.assertEqual(roundtrip["a"], DEFAULTS["a"])
        self.assertEqual(roundtrip["eval_rat_w"], DEFAULTS["eval_rat_w"])

    def test_live_and_baseline_agents_read_different_env_channels(self) -> None:
        board = make_board(time_to_play=240)
        env = {
            "Y4_WEIGHTS_JSON": json.dumps({"a": 2.1, "time_opening_cap": 4.0}),
            "Y4_BASELINE_WEIGHTS_JSON": json.dumps({"a": 0.9, "time_opening_cap": 2.0}),
        }
        with patch.dict("os.environ", env, clear=False):
            live_agent = LiveAgent(board, identity_transition(), time_left=lambda: 10.0)
            baseline_agent = BaselineAgent(board, identity_transition(), time_left=lambda: 10.0)

        self.assertAlmostEqual(live_agent.policy_engine.a, 2.1)
        self.assertAlmostEqual(baseline_agent.policy_engine.a, 0.9)
        self.assertAlmostEqual(TimeManager.phase_cap(0, live_agent.runtime_state), 4.0)
        self.assertAlmostEqual(TimeManager.phase_cap(0, baseline_agent.runtime_state), 2.0)

    def test_run_single_game_raises_on_failed_init(self) -> None:
        task = GameTask(
            candidate_weights_json=json.dumps({}),
            baseline_weights_json=None,
            opponent_name="RandomSearchBaseline",
            seed=42,
            candidate_is_a=True,
            play_time=240,
            limit_resources=False,
            catastrophic_penalty=-50.0,
        )
        fake_board = SimpleNamespace(
            winner=ResultArbiter.TIE,
            win_reason=WinReason.FAILED_INIT,
        )
        fake_result = (fake_board, [], (0, 0), (1, 1), "candidate failed", "opponent failed")
        with patch("workflows.y4_hyperopt.play_game", return_value=fake_result):
            with self.assertRaises(InfrastructureFailure):
                run_single_game(task)


if __name__ == "__main__":
    unittest.main()
