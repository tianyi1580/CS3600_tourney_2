from __future__ import annotations

import unittest
from unittest.mock import patch

import numpy as np

from common import identity_transition, make_board
from game.enums import Cell, Direction, MoveType
from game.move import Move
from Yolanda3_4.infra.runtime_state import RuntimeState
from Yolanda3_4.strategy.board_analysis import BoardAnalysis
from Yolanda3_4.strategy.expectiminimax import Expectiminimax
from Yolanda3_4.strategy.policy import PolicyEngine
from Yolanda3_4.tracking.belief import BeliefEngine


class Yolanda3_4ExpectiminimaxTests(unittest.TestCase):
    def setUp(self) -> None:
        self.board = make_board()
        self.belief = BeliefEngine(identity_transition())
        self.policy = PolicyEngine()
        self.state = RuntimeState()

    def test_expectiminimax_prefers_shared_cashout_over_setup(self) -> None:
        self.board.player_worker.position = (1, 3)
        self.board.opponent_worker.position = (7, 3)
        self.board.player_worker.turns_left = 20
        self.board.opponent_worker.turns_left = 20

        for x in range(2, 7):
            self.board.set_cell((x, 3), Cell.PRIMED)

        searcher = Expectiminimax(self.policy, BoardAnalysis(self.board))
        best_move, _value, completed_depth2 = searcher.rank_moves(
            self.board,
            [Move.prime(Direction.UP), Move.carpet(Direction.RIGHT, 5)],
            0.30,
        )

        self.assertTrue(completed_depth2)
        self.assertIsNotNone(best_move)
        self.assertEqual(best_move.move_type, MoveType.CARPET)
        self.assertEqual(best_move.roll_length, 5)

    def test_prefers_nearer_high_potential_corridor(self) -> None:
        self.board.player_worker.position = (3, 3)
        self.board.opponent_worker.position = (7, 7)
        self.board.player_worker.turns_left = 18
        self.board.set_cell((3, 3), Cell.CARPET)
        self.board.set_cell((3, 2), Cell.BLOCKED)
        self.board.set_cell((3, 4), Cell.BLOCKED)
        self.board.set_cell((2, 4), Cell.PRIMED)
        self.board.set_cell((2, 5), Cell.PRIMED)
        self.board.set_cell((2, 6), Cell.PRIMED)
        self.board.set_cell((5, 3), Cell.BLOCKED)
        self.board.set_cell((4, 2), Cell.BLOCKED)
        self.board.set_cell((4, 4), Cell.BLOCKED)
        self.belief.belief = np.full(64, 1.0 / 64.0, dtype=np.float64)

        action = self.policy.select_action(
            self.board,
            self.belief,
            self.state,
            time_left=lambda: 120.0,
        )

        self.assertEqual(action.move_type, MoveType.PLAIN)
        self.assertEqual(action.direction, Direction.LEFT)

    def test_incomplete_tree_falls_back_to_heuristic_choice(self) -> None:
        self.board.player_worker.position = (1, 3)
        self.board.opponent_worker.position = (7, 7)
        self.board.player_worker.turns_left = 20
        for x in range(2, 7):
            self.board.set_cell((x, 3), Cell.PRIMED)
        self.belief.belief = np.full(64, 1.0 / 64.0, dtype=np.float64)

        def fake_score_non_search(board, action, belief, state, **_kwargs):
            if action.move_type == MoveType.CARPET and action.roll_length == 5:
                return 12.0, {"mobility": 3.0, "immediate": 10.0, "risk": 0.0, "continuation": 0.0}
            if action.move_type == MoveType.PRIME:
                return 1.0, {"mobility": 2.0, "immediate": 1.0, "risk": 0.0, "continuation": 0.0}
            return -1.0, {"mobility": 0.0, "immediate": 0.0, "risk": 1.0, "continuation": 0.0}

        with patch.object(
            Expectiminimax,
            "rank_moves",
            return_value=(Move.prime(Direction.UP), 999.0, False),
        ), patch.object(self.policy, "score_non_search", side_effect=fake_score_non_search):
            action = self.policy.select_action(
                self.board,
                self.belief,
                self.state,
                time_left=lambda: 120.0,
            )

        self.assertEqual(action.move_type, MoveType.CARPET)
        self.assertEqual(action.roll_length, 5)

    def test_search_gate_is_preserved_when_search_ev_dominates(self) -> None:
        self.board.player_worker.position = (3, 3)
        self.board.opponent_worker.position = (7, 7)
        self.board.player_worker.turns_left = 20
        self.board.set_cell((3, 3), Cell.CARPET)
        self.belief.belief = np.zeros(64, dtype=np.float64)
        self.belief.belief[0] = 0.99

        action = self.policy.select_action(
            self.board,
            self.belief,
            self.state,
            time_left=lambda: 120.0,
        )

        self.assertEqual(action.move_type, MoveType.SEARCH)


if __name__ == "__main__":
    unittest.main()
