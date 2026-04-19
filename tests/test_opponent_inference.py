from __future__ import annotations

from collections import deque
import unittest

from common import make_board
from game.enums import MoveType
from game.move import Move
from Yolanda.tracking.opponent_observation import OpponentCategory, infer_opponent_category


def _opp_category_from_move(m: Move) -> OpponentCategory:
    if m.move_type == MoveType.SEARCH:
        return OpponentCategory.SEARCH
    if m.move_type == MoveType.PRIME:
        return OpponentCategory.PRIME
    if m.move_type == MoveType.CARPET:
        return OpponentCategory.CARPET
    return OpponentCategory.PLAIN


class OpponentInferenceTests(unittest.TestCase):
    def test_infer_non_search_replay_matches_single_candidate(self) -> None:
        """infer_opponent_category: deterministic replay from snapshot + our move (M3 adaptation)."""
        b_prev = make_board()
        moves_us = [m for m in b_prev.get_valid_moves(exclude_search=True) if b_prev.is_valid_move(m)]
        self.assertTrue(moves_us)
        m_us = moves_us[0]

        tmp = b_prev.get_copy()
        self.assertTrue(tmp.apply_move(m_us))
        tmp.reverse_perspective()
        moves_opp = [m for m in tmp.get_valid_moves(exclude_search=True) if tmp.is_valid_move(m)]
        self.assertTrue(moves_opp)
        m_opp = moves_opp[0]
        self.assertTrue(tmp.apply_move(m_opp))
        tmp.reverse_perspective()

        cat = infer_opponent_category(b_prev, m_us, tmp)
        self.assertEqual(cat, _opp_category_from_move(m_opp))

    def test_infer_search_from_opponent_search_channel(self) -> None:
        """infer_opponent_category: resolved opponent_search tuple change implies SEARCH."""
        b_prev = make_board()
        b_prev.opponent_search = (None, None)
        moves_us = [m for m in b_prev.get_valid_moves(exclude_search=True) if b_prev.is_valid_move(m)]
        m_us = moves_us[0]

        b_now = b_prev.get_copy()
        self.assertTrue(b_now.apply_move(m_us))
        b_now.reverse_perspective()
        # Opponent searches (board state may be inconsistent with real gameplay; channel drives inference).
        sm = Move.search((1, 1))
        if b_now.is_valid_move(sm):
            self.assertTrue(b_now.apply_move(sm))
            b_now.reverse_perspective()
            b_now.opponent_search = ((1, 1), False)
            cat = infer_opponent_category(b_prev, m_us, b_now)
            self.assertEqual(cat, OpponentCategory.SEARCH)

    def test_infer_non_search_with_nontrivial_channel_history(self) -> None:
        """
        infer_opponent_category should still recover non-search moves when prior search channels are populated.
        This covers replay parity with rolling channel history, not just `(None, None)` defaults.
        """
        b_prev = make_board()
        searches = deque([((6, 6), False), ((2, 2), True)], maxlen=2)
        b_prev.opponent_search = searches[-1]
        b_prev.player_search = searches[-2]

        moves_us = [m for m in b_prev.get_valid_moves(exclude_search=True) if b_prev.is_valid_move(m)]
        self.assertTrue(moves_us)
        m_us = moves_us[0]

        b_mid = b_prev.get_copy()
        self.assertTrue(b_mid.apply_move(m_us))
        searches.append((None, None))
        b_mid.reverse_perspective()
        b_mid.opponent_search = searches[-1]
        b_mid.player_search = searches[-2]

        moves_opp = [m for m in b_mid.get_valid_moves(exclude_search=True) if b_mid.is_valid_move(m)]
        self.assertTrue(moves_opp)
        m_opp = moves_opp[0]

        b_now = b_mid.get_copy()
        self.assertTrue(b_now.apply_move(m_opp))
        searches.append((None, None))
        b_now.reverse_perspective()
        b_now.opponent_search = searches[-1]
        b_now.player_search = searches[-2]

        cat = infer_opponent_category(b_prev, m_us, b_now)
        self.assertEqual(cat, _opp_category_from_move(m_opp))


if __name__ == "__main__":
    unittest.main()
