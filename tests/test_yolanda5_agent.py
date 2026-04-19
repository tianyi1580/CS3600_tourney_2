from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from common import identity_transition, make_board
from game.enums import Noise
from Yolanda5.agent import ConfiguredPlayerAgent, PlayerAgent
from Yolanda5.infra.weights import load_weights


class Yolanda5AgentTests(unittest.TestCase):
    def test_commentate_reports_env_weight_profile(self) -> None:
        board = make_board(time_to_play=240)
        with patch.dict("os.environ", {"Y5_WEIGHTS_JSON": json.dumps({"eval_chain_w": 1.1})}, clear=False):
            agent = PlayerAgent(board, identity_transition(), time_left=lambda: 20.0)
        msg = agent.commentate()
        self.assertIn("Yolanda5", msg)
        self.assertIn("weights=env", msg)

    def test_play_returns_legal_move(self) -> None:
        board = make_board(time_to_play=240)
        agent = PlayerAgent(board, identity_transition(), time_left=lambda: 20.0)

        mv = agent.play(
            board,
            sensor_data=(Noise.SQUEAK, 4),
            time_left=lambda: 120.0,
        )

        self.assertTrue(board.is_valid_move(mv))

    def test_load_weights_falls_back_to_package_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "weights.json").write_text('{"eval_chain_w": 1.4}\n', encoding="utf-8")
            with patch.dict(os.environ, {}, clear=False):
                weights, source = load_weights(package_root=root, allow_env=False)

        self.assertEqual(source, "package")
        self.assertEqual(weights["eval_chain_w"], 1.4)

    def test_configured_agent_can_disable_env_weights(self) -> None:
        board = make_board(time_to_play=240)
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "weights.json").write_text('{"eval_chain_w": 1.25}\n', encoding="utf-8")
            with patch.dict("os.environ", {"Y5_WEIGHTS_JSON": json.dumps({"eval_chain_w": 1.5})}, clear=False):
                agent = ConfiguredPlayerAgent(
                    board,
                    identity_transition(),
                    time_left=lambda: 20.0,
                    weights_root=root,
                    allow_env_weights=False,
                )

        self.assertEqual(agent.runtime_state.weights_profile, "package")
        self.assertAlmostEqual(agent.policy_engine.eval_chain_w, 1.25)


if __name__ == "__main__":
    unittest.main()
