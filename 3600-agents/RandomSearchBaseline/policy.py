from __future__ import annotations

import random

from game.board import Board
from game.enums import MoveType
from game.move import Move


class RandomSearchPolicy:
    """Minimal valid policy used only as a sanity-floor opponent."""

    def select_action(self, board: Board) -> Move:
        non_search_moves = board.get_valid_moves(exclude_search=True)
        search_moves = [move for move in board.get_valid_moves(exclude_search=False) if move.move_type == MoveType.SEARCH]

        # Bias toward random search often enough that tuned agents must punish it.
        if search_moves and (not non_search_moves or random.random() < 0.25):
            return random.choice(search_moves)
        if non_search_moves:
            return random.choice(non_search_moves)
        return search_moves[0]
