from __future__ import annotations

import re
import unittest
from unittest.mock import patch

from common import identity_transition, make_board
from game.enums import Noise
from Yolanda.agent import PlayerAgent


class AgentContractTests(unittest.TestCase):
    def test_constructor_reads_constructor_budget_time_left(self) -> None:
        board = make_board(time_to_play=360)
        agent = PlayerAgent(board, identity_transition(), time_left=lambda: 10.0)
        self.assertEqual(agent.runtime_state.constructor_budget_remaining, 10.0)
        self.assertEqual(agent.runtime_state.initial_total_budget, 360.0)

    def test_play_returns_legal_move(self) -> None:
        board = make_board(time_to_play=240)
        agent = PlayerAgent(board, identity_transition(), time_left=lambda: 20.0)

        mv = agent.play(
            board,
            sensor_data=(Noise.SQUEAK, 4),
            time_left=lambda: 120.0,
        )

        self.assertTrue(board.is_valid_move(mv))

    def test_constructor_respects_ablation_env_toggles(self) -> None:
        board = make_board(time_to_play=240)
        with patch.dict(
            "os.environ",
            {"YOLANDA_ENABLE_OPPONENT_MODEL": "0", "YOLANDA_ENABLE_ADAPTIVE_MARGIN": "false"},
            clear=False,
        ):
            agent = PlayerAgent(board, identity_transition(), time_left=lambda: 20.0)
        self.assertFalse(agent.runtime_state.enable_opponent_model)
        self.assertFalse(agent.runtime_state.enable_adaptive_margin)

    def test_commentate_includes_build_tag(self) -> None:
        board = make_board(time_to_play=240)
        agent = PlayerAgent(board, identity_transition(), time_left=lambda: 20.0)
        msg = agent.commentate()
        self.assertRegex(msg, r"build=fp1:[0-9a-f]{12}")


if __name__ == "__main__":
    unittest.main()
