from __future__ import annotations

import random
import unittest

from common import make_board
from game.enums import Cell
from Yolanda6.strategy.bitboard_state import BitboardAdapter, move_signature
from Yolanda6.strategy.voronoi import VoronoiSnapshot


def _evolve_board(seed: int, steps: int = 6):
    rng = random.Random(seed)
    board = make_board()
    for _ in range(steps):
        moves = board.get_valid_moves(exclude_search=True)
        if not moves:
            break
        move = rng.choice(moves)
        board = board.forecast_move(move, check_ok=True)
        if board is None:
            break
        board.reverse_perspective()
    return board


class Yolanda6BitboardTests(unittest.TestCase):
    def test_move_generation_matches_engine_on_reachable_states(self) -> None:
        for seed in range(8):
            board = _evolve_board(seed)
            state = BitboardAdapter.from_board(board)
            board_moves = sorted(move_signature(move) for move in board.get_valid_moves(exclude_search=True))
            state_moves = sorted(move_signature(move) for move in state.valid_non_search_moves())
            self.assertEqual(board_moves, state_moves)

    def test_apply_and_restore_match_engine_forecast(self) -> None:
        for seed in range(4):
            board = _evolve_board(100 + seed, steps=5)
            state = BitboardAdapter.from_board(board)
            original_signature = (
                state.space_mask,
                state.primed_mask,
                state.carpet_mask,
                state.blocked_mask,
                state.player_idx,
                state.opponent_idx,
                state.player_points,
                state.opponent_points,
                state.player_turns_left,
                state.opponent_turns_left,
                state.turn_count,
            )
            for move in board.get_valid_moves(exclude_search=True):
                token = state.apply_move(move)
                self.assertIsNotNone(token)
                board_after = board.forecast_move(move, check_ok=True)
                self.assertIsNotNone(board_after)
                board_after.reverse_perspective()
                self.assertEqual(state.space_mask, board_after._space_mask)
                self.assertEqual(state.primed_mask, board_after._primed_mask)
                self.assertEqual(state.carpet_mask, board_after._carpet_mask)
                self.assertEqual(state.blocked_mask, board_after._blocked_mask)
                self.assertEqual(state.player_loc(), board_after.player_worker.get_location())
                self.assertEqual(state.opponent_loc(), board_after.opponent_worker.get_location())
                self.assertEqual(state.player_points, board_after.player_worker.get_points())
                self.assertEqual(state.opponent_points, board_after.opponent_worker.get_points())
                state.restore(token)
                restored = (
                    state.space_mask,
                    state.primed_mask,
                    state.carpet_mask,
                    state.blocked_mask,
                    state.player_idx,
                    state.opponent_idx,
                    state.player_points,
                    state.opponent_points,
                    state.player_turns_left,
                    state.opponent_turns_left,
                    state.turn_count,
                )
                self.assertEqual(restored, original_signature)

    def test_voronoi_marks_shared_chain_as_contested(self) -> None:
        board = make_board()
        board.player_worker.position = (1, 2)
        board.opponent_worker.position = (1, 4)
        for x in (2, 3, 4):
            board.set_cell((x, 3), Cell.PRIMED)
        snapshot = VoronoiSnapshot.from_state(BitboardAdapter.from_board(board))
        self.assertTrue(snapshot.entries)
        self.assertTrue(any(entry.zone == "contested" for entry in snapshot.entries))


if __name__ == "__main__":
    unittest.main()
