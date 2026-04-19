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
        self.policy_engine = PolicyEngine(
            enable_lead_aware_centrality=_env_flag("Y3_ENABLE_LEAD_AWARE_CENTRALITY", True),
            mid_lead_centrality_scale=_env_float("Y3_MID_LEAD_CENTRALITY_SCALE", 0.7),
            mid_trailing_centrality_scale=_env_float("Y3_MID_TRAILING_CENTRALITY_SCALE", 1.2),
            opening_centrality_scale=_env_float("Y3_OPENING_CENTRALITY_SCALE", 1.5),
            late_centrality_scale=_env_float("Y3_LATE_CENTRALITY_SCALE", 0.3),
            mid_lead_space_bonus=_env_float("Y3_MID_LEAD_SPACE_BONUS", 0.5),
            enable_threatened_cashout_bonus=_env_flag("Y3_ENABLE_THREATENED_CASHOUT", True),
            threatened_cashout_min_roll=max(1, _env_int("Y3_THREAT_CASHOUT_MIN_ROLL", 4)),
            threatened_cashout_opp_dist=max(0, _env_int("Y3_THREAT_CASHOUT_OPP_DIST", 3)),
            threatened_cashout_bonus=_env_float("Y3_THREAT_CASHOUT_BONUS", 2.0),
            enable_opponent_chain_sabotage=_env_flag("Y3_ENABLE_SABOTAGE", True),
            sabotage_min_chain_len=max(1, _env_int("Y3_SABOTAGE_MIN_CHAIN_LEN", 3)),
            sabotage_opp_dist=max(0, _env_int("Y3_SABOTAGE_OPP_DIST", 3)),
            sabotage_bonus=_env_float("Y3_SABOTAGE_BONUS", 3.5),
            enable_fast_search_shortcut=_env_flag("Y3_ENABLE_FAST_SEARCH", False),
            fast_search_prob_threshold=_env_float("Y3_FAST_SEARCH_PROB", 0.8),
            fast_search_max_carpet_points=_env_float("Y3_FAST_SEARCH_MAX_CARPET", 12.0),
        )

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
            "Yolanda3: Carpet-first strategy + opponent chain disruption "
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


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default
