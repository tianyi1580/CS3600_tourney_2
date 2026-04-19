from __future__ import annotations

import unittest

import numpy as np

from common import identity_transition, make_board
from game.enums import Cell, Direction, MoveType
from game.move import Move
from Yolanda3_1.infra.runtime_state import RuntimeState
from Yolanda3_1.strategy.board_analysis import BoardAnalysis
from Yolanda3_1.strategy.policy import PolicyEngine
from Yolanda3_1.tracking.belief import BeliefEngine


class Yolanda31TacticalRegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = PolicyEngine()
        self.belief = BeliefEngine(identity_transition())
        self.belief.belief = np.full(64, 1.0 / 64.0, dtype=np.float64)  # keep search EV non-positive
        self.state = RuntimeState()
        self.state.enable_opponent_model = False

    def test_l_shape_cashout_selected_under_contest(self) -> None:
        board = make_board()
        board.player_worker.position = (2, 3)
        board.opponent_worker.position = (5, 2)
        board.player_worker.turns_left = 20
        board.set_cell((3, 3), Cell.PRIMED)
        board.set_cell((4, 3), Cell.PRIMED)
        board.set_cell((5, 3), Cell.PRIMED)
        board.set_cell((4, 2), Cell.PRIMED)
        board.set_cell((4, 1), Cell.PRIMED)

        action = self.policy.select_action(board, self.belief, self.state, time_left=lambda: 120.0)
        self.assertEqual(action.move_type, MoveType.CARPET)
        self.assertGreaterEqual(action.roll_length, 3)

    def test_long_line_threat_forces_immediate_carpet(self) -> None:
        board = make_board()
        board.player_worker.position = (1, 4)
        board.opponent_worker.position = (6, 5)
        board.player_worker.turns_left = 18
        for x in (2, 3, 4, 5, 6):
            board.set_cell((x, 4), Cell.PRIMED)

        action = self.policy.select_action(board, self.belief, self.state, time_left=lambda: 120.0)
        self.assertEqual(action.move_type, MoveType.CARPET)
        self.assertGreaterEqual(action.roll_length, 4)

    def test_two_ply_disruption_lowers_chain_survival(self) -> None:
        board = make_board()
        board.player_worker.position = (2, 4)
        board.opponent_worker.position = (5, 4)
        board.player_worker.turns_left = 16
        for x in (3, 4, 5):
            board.set_cell((x, 4), Cell.PRIMED)

        survival, immediate_break, two_ply_break = self.policy._chain_survival_summary(
            board,
            Move.carpet(Direction.RIGHT, 3),
            deep_eval=True,
        )
        self.assertTrue(immediate_break or two_ply_break > 0.0)
        self.assertLess(survival, 0.75)

    def test_cluster_profiles_and_contention_bonus_use_access_times(self) -> None:
        board = make_board()
        board.player_worker.position = (1, 3)
        board.opponent_worker.position = (5, 3)
        board.player_worker.turns_left = 14
        board.set_cell((2, 3), Cell.PRIMED)
        board.set_cell((3, 3), Cell.PRIMED)
        board.set_cell((4, 3), Cell.PRIMED)
        board.set_cell((3, 2), Cell.PRIMED)

        snap = BoardAnalysis(board)
        profiles = snap.primed_cluster_profiles()
        self.assertTrue(any(float(p["cluster_value"]) >= 4.0 for p in profiles))

        bonus = self.policy._cluster_contention_bonus(
            board,
            Move.carpet(Direction.RIGHT, 3),
            dest=(4, 3),
            analysis=snap,
        )
        self.assertGreater(bonus, 0.0)


if __name__ == "__main__":
    unittest.main()
