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
from .infra.weights import load_weights, phase_multiplier_tuple
from .strategy.policy import PolicyEngine
from .infra.runtime_state import RuntimeState
from .infra.time_manager import TimeManager


class ConfiguredPlayerAgent:
    """
    Engine-facing agent entrypoint.

    The constructor, play, and commentate signatures are intentionally preserved.
    """

    def __init__(
        self,
        board,
        transition_matrix=None,
        time_left: Callable = None,
        *,
        weight_env_var: str = "Y4_WEIGHTS_JSON",
        weights_root: Path | None = None,
        weights_file_name: str = "weights.json",
        allow_env_weights: bool = True,
        weights_profile: str = "live",
        commentate_name: str = "Yolanda4",
        fingerprint_root: Path | None = None,
    ):
        if transition_matrix is None:
            transition_matrix = np.eye(BOARD_SIZE * BOARD_SIZE, dtype=np.float64)

        package_root = weights_root or Path(__file__).resolve().parent
        code_root = fingerprint_root or Path(__file__).resolve().parent
        weights = load_weights(
            package_root=package_root,
            env_var=weight_env_var,
            weights_file_name=weights_file_name,
            allow_env=allow_env_weights,
        )

        self.runtime_state = RuntimeState()
        self.runtime_state.use_single_step = board.is_player_a_turn
        self.runtime_state.weights_profile = weights_profile
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
        self.runtime_state.time_opening_multiplier = weights["time_opening_multiplier"]
        self.runtime_state.time_mid_multiplier = weights["time_mid_multiplier"]
        self.runtime_state.time_late_multiplier = weights["time_late_multiplier"]
        self.runtime_state.time_opening_cap = weights["time_opening_cap"]
        self.runtime_state.time_mid_cap = weights["time_mid_cap"]
        self.runtime_state.time_late_cap = weights["time_late_cap"]

        self.belief_engine = BeliefEngine(np.asarray(transition_matrix, dtype=np.float64))
        self.policy_engine = PolicyEngine(
            a=weights["a"],
            b=weights["b"],
            c=weights["c"],
            d=weights["d"],
            f=weights["f"],
            g=weights["g"],
            opp_response_weight=weights["opp_response_weight"],
            opening_mults=phase_multiplier_tuple(weights, "opening"),
            mid_mults=phase_multiplier_tuple(weights, "mid"),
            late_mults=phase_multiplier_tuple(weights, "late"),
            farmable_ev_scale=weights["farmable_ev_scale"],
            farmable_margin_base=weights["farmable_margin_base"],
            farmable_margin_slope=weights["farmable_margin_slope"],
            nonfarm_margin_base=weights["nonfarm_margin_base"],
            nonfarm_margin_slope=weights["nonfarm_margin_slope"],
            eval_potential_w=weights["eval_potential_w"],
            eval_chain_w=weights["eval_chain_w"],
            eval_exit_w=weights["eval_exit_w"],
            eval_entry_adv_w=weights["eval_entry_adv_w"],
            eval_trap_w=weights["eval_trap_w"],
            eval_rat_w=weights["eval_rat_w"],
            rat_nearby_w=weights["rat_nearby_w"],
            rat_peak_w=weights["rat_peak_w"],
            rat_peak_thresh=weights["rat_peak_thresh"],
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
        self.runtime_state.build_fingerprint = compute_build_fingerprint(bot_dir=code_root)
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
            f"{self.commentate_name}: Advanced Minimax + Rat-Aware Eval + AB Pruning "
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
    """Default Yolanda4 entrypoint with live/offline-tunable weights enabled."""

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
