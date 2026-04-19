from __future__ import annotations

from collections.abc import Callable
import os
from typing import Tuple

import numpy as np

from game import board as board_module
from game.enums import BOARD_SIZE

from .tracking.belief import BeliefEngine
from .infra.build_fingerprint import FINGERPRINT_SCHEMA_VERSION, compute_build_fingerprint
from .strategy.policy import PolicyEngine
from .infra.runtime_state import RuntimeState
from .infra.time_manager import TimeManager


class PlayerAgent:
    """
    Engine-facing agent entrypoint.

    The constructor, play, and commentate signatures are intentionally preserved.
    """

    def __init__(self, board, transition_matrix=None, time_left: Callable = None):
        if transition_matrix is None:
            transition_matrix = np.eye(BOARD_SIZE * BOARD_SIZE, dtype=np.float64)

        self.runtime_state = RuntimeState()
        self.runtime_state.use_single_step = board.is_player_a_turn
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

        # T-matrix farmability check (§12 of movement strategy doc).
        # b_reset is already computed by BeliefEngine.__post_init__; just read the peak.
        rat_concentration = float(np.max(self.belief_engine.reset_prior))
        self.runtime_state.rat_concentration = rat_concentration
        self.runtime_state.farmable_rat = rat_concentration > 0.25

        # Ablation/runtime toggles for controlled M3 comparisons.
        self.runtime_state.enable_opponent_model = _env_flag("YOLANDA_ENABLE_OPPONENT_MODEL", True)
        self.runtime_state.build_fingerprint = compute_build_fingerprint()

        pe = self.policy_engine
        rs = self.runtime_state
        rs.policy_base_a = pe.a
        rs.policy_base_c = pe.c
        rs.policy_base_d = pe.d
        rs.policy_base_f = pe.f
        rs.effective_a = pe.a
        rs.effective_c = pe.c
        rs.effective_d = pe.d
        rs.effective_f = pe.f

    def commentate(self):
        rs = self.runtime_state
        return (
            "Yolanda_Mitchell: Streak focus + center avoidance "
            f"| build={FINGERPRINT_SCHEMA_VERSION}:{rs.build_fingerprint} "
            f"| opponent_model={int(rs.enable_opponent_model)}"
        )

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
                self.belief_engine.predict(self.runtime_state.use_single_step, self.runtime_state.opp_miss_cell)
                self.runtime_state.use_single_step = False
                self.runtime_state.opp_miss_cell = None
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


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    val = raw.strip().lower()
    if val in {"1", "true", "yes", "on"}:
        return True
    if val in {"0", "false", "no", "off"}:
        return False
    return default
