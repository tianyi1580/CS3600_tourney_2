from __future__ import annotations

from collections.abc import Callable
import os
from pathlib import Path
from typing import Tuple

import numpy as np

from game import board as board_module
from game.enums import BOARD_SIZE

from .tracking.belief import BeliefEngine
from .infra.build_fingerprint import FINGERPRINT_SCHEMA_VERSION, compute_build_fingerprint
from .infra.runtime_state import RuntimeState
from .infra.time_manager import TimeManager
from .infra.weights import load_weights
from .strategy.policy import PolicyEngine


class ConfiguredPlayerAgent:
    """Engine-facing entrypoint with safe local/env weight loading."""

    def __init__(
        self,
        board,
        transition_matrix=None,
        time_left: Callable = None,
        *,
        weight_env_var: str = "YP2_WEIGHTS_JSON",
        weights_root: Path | None = None,
        weights_file_name: str = "weights.json",
        allow_env_weights: bool = True,
        commentate_name: str = "yolanda_prime_v2",
        fingerprint_root: Path | None = None,
    ):
        if transition_matrix is None:
            transition_matrix = np.eye(BOARD_SIZE * BOARD_SIZE, dtype=np.float64)

        package_root = weights_root or Path(__file__).resolve().parent
        code_root = fingerprint_root or package_root
        weights, weight_source = load_weights(
            package_root=package_root,
            env_var=weight_env_var,
            weights_file_name=weights_file_name,
            allow_env=allow_env_weights,
        )

        self.runtime_state = RuntimeState()
        self.runtime_state.use_single_step = board.is_player_a_turn
        self.runtime_state.weights_profile = weight_source
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
            a=weights["a"],
            b=weights["b"],
            c=weights["c"],
            d=weights["d"],
            f=weights["f"],
            g=weights["g"],
            enable_lead_aware_centrality=_env_flag("Y3_ENABLE_LEAD_AWARE_CENTRALITY", True),
            mid_lead_centrality_scale=weights["mid_lead_centrality_scale"],
            mid_trailing_centrality_scale=weights["mid_trailing_centrality_scale"],
            opening_centrality_scale=weights["opening_centrality_scale"],
            late_centrality_scale=weights["late_centrality_scale"],
            mid_lead_space_bonus=weights["mid_lead_space_bonus"],
            enable_threatened_cashout_bonus=_env_flag("Y3_ENABLE_THREATENED_CASHOUT", True),
            threatened_cashout_min_roll=max(1, _env_int("Y3_THREAT_CASHOUT_MIN_ROLL", 4)),
            threatened_cashout_opp_dist=max(0, _env_int("Y3_THREAT_CASHOUT_OPP_DIST", 3)),
            threatened_cashout_bonus=weights["threatened_cashout_bonus"],
            enable_opponent_chain_sabotage=_env_flag("Y3_ENABLE_SABOTAGE", True),
            sabotage_min_chain_len=max(1, _env_int("Y3_SABOTAGE_MIN_CHAIN_LEN", 3)),
            sabotage_opp_dist=max(0, _env_int("Y3_SABOTAGE_OPP_DIST", 3)),
            sabotage_bonus=weights["sabotage_bonus"],
            enable_fast_search_shortcut=_env_flag("Y3_ENABLE_FAST_SEARCH", False),
            fast_search_prob_threshold=weights["fast_search_prob_threshold"],
            fast_search_max_carpet_points=weights["fast_search_max_carpet_points"],
            opening_mult_a=weights["opening_mult_a"],
            opening_mult_b=weights["opening_mult_b"],
            opening_mult_c=weights["opening_mult_c"],
            opening_mult_d=weights["opening_mult_d"],
            opening_mult_f=weights["opening_mult_f"],
            mid_mult_a=weights["mid_mult_a"],
            mid_mult_b=weights["mid_mult_b"],
            mid_mult_c=weights["mid_mult_c"],
            mid_mult_d=weights["mid_mult_d"],
            mid_mult_f=weights["mid_mult_f"],
            late_mult_a=weights["late_mult_a"],
            late_mult_b=weights["late_mult_b"],
            late_mult_c=weights["late_mult_c"],
            late_mult_d=weights["late_mult_d"],
            late_mult_f=weights["late_mult_f"],
            search_gate_base_farm=weights["search_gate_base_farm"],
            search_gate_slope_farm=weights["search_gate_slope_farm"],
            search_gate_base_nonfarm=weights["search_gate_base_nonfarm"],
            search_gate_slope_nonfarm=weights["search_gate_slope_nonfarm"],
            carpet_counter_floor_early=weights["carpet_counter_floor_early"],
            carpet_counter_floor_late=weights["carpet_counter_floor_late"],
            carpet_counter_floor_pressure_gain=weights["carpet_counter_floor_pressure_gain"],
            lookahead_carpet_risk_penalty=weights["lookahead_carpet_risk_penalty"],
        )

        # T-matrix farmability check (§12 of movement strategy doc).
        # b_reset is already computed by BeliefEngine.__post_init__; just read the peak.
        rat_concentration = float(np.max(self.belief_engine.reset_prior))
        self.runtime_state.rat_concentration = rat_concentration
        self.runtime_state.farmable_rat = rat_concentration > 0.25

        # Ablation/runtime toggles for controlled M3 comparisons.
        self.runtime_state.enable_opponent_model = _env_flag("YOLANDA_ENABLE_OPPONENT_MODEL", True)
        self.runtime_state.build_fingerprint = compute_build_fingerprint(bot_dir=code_root)
        self.runtime_state.time_opening_multiplier = weights["time_opening_multiplier"]
        self.runtime_state.time_mid_multiplier = weights["time_mid_multiplier"]
        self.runtime_state.time_late_multiplier = weights["time_late_multiplier"]
        self.runtime_state.time_opening_cap = weights["time_opening_cap"]
        self.runtime_state.time_mid_cap = weights["time_mid_cap"]
        self.runtime_state.time_late_cap = weights["time_late_cap"]
        self.commentate_name = commentate_name

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
            f"{self.commentate_name}: prime tactical search + adaptive policy "
            f"| build={FINGERPRINT_SCHEMA_VERSION}:{rs.build_fingerprint} "
            f"| weights={rs.weights_profile} "
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


class PlayerAgent(ConfiguredPlayerAgent):
    """Default agent entrypoint with safe local/env weight loading."""

    def __init__(self, board, transition_matrix=None, time_left: Callable = None):
        super().__init__(board, transition_matrix, time_left)


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
