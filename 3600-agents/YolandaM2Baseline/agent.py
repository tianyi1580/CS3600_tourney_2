from __future__ import annotations

from collections.abc import Callable
from typing import Tuple

import numpy as np

from game import board as board_module
from game.enums import BOARD_SIZE

from .belief import BeliefEngine
from .policy import PolicyEngine
from .runtime_state import RuntimeState
from .time_manager import TimeManager


class PlayerAgent:
    """
    Engine-facing agent entrypoint.

    The constructor, play, and commentate signatures are intentionally preserved.
    """

    def __init__(self, board, transition_matrix=None, time_left: Callable = None):
        if transition_matrix is None:
            transition_matrix = np.eye(BOARD_SIZE * BOARD_SIZE, dtype=np.float64)

        self.runtime_state = RuntimeState()
        # Constructor `time_left()` reports constructor budget, not game budget.
        if callable(time_left):
            try:
                self.runtime_state.constructor_budget_remaining = float(time_left())
            except Exception:
                self.runtime_state.constructor_budget_remaining = 0.0
        self.runtime_state.initial_total_budget = float(board.player_worker.time_left)
        self.runtime_state.emergency_floor_total = TimeManager.compute_emergency_floor(
            self.runtime_state.initial_total_budget
        )

        self.belief_engine = BeliefEngine(np.asarray(transition_matrix, dtype=np.float64))
        self.policy_engine = PolicyEngine()

    def commentate(self):
        return "frozen M2 baseline (pre-M3): explicit search + belief + time-safe policy (no adaptation)"

    def play(
        self,
        board: board_module.Board,
        sensor_data: Tuple,
        time_left: Callable,
    ):
        try:
            self.policy_engine.apply_search_channels(board, self.belief_engine, self.runtime_state)

            if isinstance(sensor_data, tuple) and len(sensor_data) == 2:
                noise, estimated_distance = sensor_data
                self.belief_engine.predict()
                self.belief_engine.update(noise, estimated_distance, board)

            return self.policy_engine.select_action(
                board,
                self.belief_engine,
                self.runtime_state,
                time_left,
            )
        except Exception:
            safe_moves = board.get_valid_moves(exclude_search=True)
            if safe_moves:
                return safe_moves[0]
            return board.get_valid_moves(exclude_search=False)[0]
