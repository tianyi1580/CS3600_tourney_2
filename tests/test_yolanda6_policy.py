from __future__ import annotations

import unittest
from unittest.mock import patch

import numpy as np

from common import identity_transition, make_board
from game.enums import Cell, Direction, MoveType
from game.move import Move
from Yolanda6.infra.runtime_state import RuntimeState
from Yolanda6.strategy.policy import PolicyEngine
from Yolanda6.tracking.belief import BeliefEngine


class Yolanda6PolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.board = make_board()
        self.policy = PolicyEngine()
        self.belief = BeliefEngine(identity_transition())

    def test_select_action_returns_valid_move(self) -> None:
        action = self.policy.select_action(self.board, self.belief, RuntimeState(), time_left=lambda: 120.0)
        self.assertTrue(self.board.is_valid_move(action))

    def test_contested_cashout_beats_passive_play(self) -> None:
        board = make_board()
        board.player_worker.position = (1, 2)
        board.opponent_worker.position = (5, 2)
        for x in (2, 3, 4):
            board.set_cell((x, 2), Cell.PRIMED)
        self.belief.belief[:] = 1.0 / 64.0
        action = self.policy.select_action(board, self.belief, RuntimeState(), time_left=lambda: 120.0)
        self.assertEqual(action.move_type, MoveType.CARPET)
        self.assertEqual(action.direction, Direction.RIGHT)
        self.assertGreaterEqual(action.roll_length, 2)

    def test_threat_adjusted_search_requires_floor_probability(self) -> None:
        board = make_board()
        runtime = RuntimeState()
        runtime.observed_turns = 10
        runtime.opp_search_attempts = 6
        runtime.opp_search_correct = 3
        self.belief.belief[:] = 0.0
        idx = 0
        self.belief.belief[idx] = 0.39

        with patch("Yolanda6.strategy.policy.BitboardSearch.rank_moves", return_value=(Move.plain(Direction.UP), 0.8, 1, {})), patch.object(
            PolicyEngine,
            "_opponent_denial_value",
            return_value=1.0,
        ):
            action = self.policy.select_action(board, self.belief, runtime, time_left=lambda: 120.0)
        self.assertNotEqual(action.move_type, MoveType.SEARCH)

        self.belief.belief[:] = 0.0
        self.belief.belief[idx] = 0.41
        with patch("Yolanda6.strategy.policy.BitboardSearch.rank_moves", return_value=(Move.plain(Direction.UP), 0.8, 1, {})), patch.object(
            PolicyEngine,
            "_opponent_denial_value",
            return_value=1.0,
        ):
            action = self.policy.select_action(board, self.belief, runtime, time_left=lambda: 120.0)
        self.assertEqual(action.move_type, MoveType.SEARCH)

    def test_low_time_uses_legal_emergency_fallback(self) -> None:
        runtime = RuntimeState()
        runtime.initial_total_budget = 240.0
        runtime.emergency_floor_total = 3.0
        action = self.policy.select_action(self.board, self.belief, runtime, time_left=lambda: 2.5)
        self.assertTrue(self.board.is_valid_move(action))


if __name__ == "__main__":
    unittest.main()
