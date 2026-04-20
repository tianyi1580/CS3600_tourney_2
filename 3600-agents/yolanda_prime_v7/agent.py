"""Yolanda Prime v4 agent entrypoint.

The heavy lifting happens inside `strategy.orchestrator.Orchestrator`; this
module is a thin shim that wires the engine-level contract to our internal
pipeline and handles defensive fallback."""
from __future__ import annotations

from collections.abc import Callable
import os
from pathlib import Path
from typing import Tuple

import numpy as np

from game import board as board_module
from game.enums import BOARD_SIZE

from .infra.build_fingerprint import FINGERPRINT_SCHEMA_VERSION, compute_build_fingerprint
from .infra.runtime_state import RuntimeState
from .infra.time_manager import TimeManager
from .infra.weights import load_weights
from .strategy.orchestrator import Orchestrator
from .tracking.belief import BeliefEngine


class ConfiguredPlayerAgent:
    """Engine-facing entrypoint with safe local/env weight loading."""

    def __init__(
        self,
        board,
        transition_matrix=None,
        time_left: Callable | None = None,
        *,
        weight_env_var: str = "YP4_WEIGHTS_JSON",
        weights_root: Path | None = None,
        weights_file_name: str = "weights.json",
        allow_env_weights: bool = True,
        commentate_name: str = "yolanda_prime_v5_1",
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

        self.weights = weights
        self.runtime_state = RuntimeState()
        self.runtime_state.use_single_step = board.is_player_a_turn
        self.runtime_state.weights_profile = weight_source
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

        rat_concentration = float(np.max(self.belief_engine.reset_prior))
        self.runtime_state.rat_concentration = rat_concentration
        self.runtime_state.farmable_rat = rat_concentration > 0.25

        self.runtime_state.build_fingerprint = compute_build_fingerprint(bot_dir=code_root)
        self.commentate_name = commentate_name

        self.orchestrator = Orchestrator(weights=weights, enable_debug=_env_flag("YP4_DEBUG", False))

    def commentate(self) -> str:
        rs = self.runtime_state
        return (
            f"{self.commentate_name}: bitboard ID+PVS | territory voronoi "
            f"| build={FINGERPRINT_SCHEMA_VERSION}:{rs.build_fingerprint} "
            f"| weights={rs.weights_profile}"
        )

    def play(
        self,
        board: board_module.Board,
        sensor_data: Tuple,
        time_left: Callable,
    ):
        try:
            return self.orchestrator.select_action(
                board=board,
                belief=self.belief_engine,
                runtime=self.runtime_state,
                sensor_data=sensor_data,
                time_left=time_left,
            )
        except Exception:
            safe_moves = board.get_valid_moves(exclude_search=True)
            if safe_moves:
                return safe_moves[0]
            return board.get_valid_moves(exclude_search=False)[0]


class PlayerAgent(ConfiguredPlayerAgent):
    def __init__(self, board, transition_matrix=None, time_left: Callable | None = None):
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
