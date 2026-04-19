from __future__ import annotations

from collections.abc import Callable
from typing import Tuple

import numpy as np

from game import board as board_module
from game.enums import BOARD_SIZE

from .policy import RandomSearchPolicy


class PlayerAgent:
    """Deliberately weak floor baseline: random tactical move or random search."""

    def __init__(self, board, transition_matrix=None, time_left: Callable = None):
        if transition_matrix is None:
            transition_matrix = np.eye(BOARD_SIZE * BOARD_SIZE, dtype=np.float64)
        self.policy_engine = RandomSearchPolicy()

    def commentate(self):
        return "RandomSearchBaseline: random legal move / random legal search"

    def play(
        self,
        board: board_module.Board,
        sensor_data: Tuple,
        time_left: Callable,
    ):
        return self.policy_engine.select_action(board)
