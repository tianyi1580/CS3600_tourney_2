from __future__ import annotations

import unittest

from common import identity_transition, make_board
from game.enums import MoveType
from game.move import Move
from Yolanda.tracking.belief import BeliefEngine
from Yolanda.strategy.policy import PolicyEngine


class DiscrepancyContractTests(unittest.TestCase):
    def test_board_default_move_generation_excludes_search(self) -> None:
        board = make_board()
        moves_default = board.get_valid_moves()
        self.assertFalse(any(m.move_type == MoveType.SEARCH for m in moves_default))

        moves_with_search = board.get_valid_moves(exclude_search=False)
        self.assertTrue(any(m.move_type == MoveType.SEARCH for m in moves_with_search))

    def test_search_scoring_not_applied_in_board_apply_move(self) -> None:
        board = make_board()
        before = board.player_worker.get_points()
        ok = board.apply_move(Move.search((0, 0)), timer=0.01, check_ok=True)
        after = board.opponent_worker.get_points()  # perspective flips in end_turn

        self.assertTrue(ok)
        self.assertEqual(before, after)

    def test_policy_search_generation_prevents_invalid_searches(self) -> None:
        board = make_board()
        belief = BeliefEngine(identity_transition())
        policy = PolicyEngine()

        candidates = policy.generate_candidates(board, belief)
        for move in candidates:
            self.assertTrue(board.is_valid_move(move))


if __name__ == "__main__":
    unittest.main()
