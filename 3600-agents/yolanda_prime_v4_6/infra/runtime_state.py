from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Optional, Tuple

from game.move import Move

from ..tracking.opponent_observation import OpponentCategory


@dataclass
class RuntimeState:
    """Shared mutable policy state kept across turns for yolanda_prime_v3."""

    constructor_budget_remaining: float = 0.0
    initial_total_budget: float = 240.0
    emergency_floor_total: float = 1.2

    use_single_step: bool = False
    opp_miss_cell: tuple[int, int] | None = None

    observed_turns: int = 0
    opp_turn_buffer: deque[tuple[OpponentCategory | None, int]] = field(
        default_factory=lambda: deque(maxlen=12)
    )
    opp_search_attempts: int = 0
    opp_search_correct: int = 0
    behavior_entropy_norm: float = 0.0

    build_fingerprint: str = ""
    weights_profile: str = "default"

    # T-matrix farmability check: concentrated stationary => rat-farming signal.
    farmable_rat: bool = False
    rat_concentration: float = 0.0

    # Search-gate / recovery hysteresis.
    plies_as_player: int = 0
    last_search_confidence: float = 0.0
    last_recovery_mode: str = "neutral"

    # Snapshot infrastructure for opponent_observation.
    snapshot_at_our_turn_start: Any = None  # Board | None; avoid circular import.
    last_own_move: Optional[Move] = None

    fallback_move: Optional[Move] = None
    fallback_turn: int = -1

    last_opponent_search: Tuple[object, object] = field(default_factory=lambda: (None, None))
    last_player_search: Tuple[object, object] = field(default_factory=lambda: (None, None))

    recent_positions: deque[tuple[int, int]] = field(
        default_factory=lambda: deque(maxlen=4)
    )
    recent_modes: deque[str] = field(default_factory=lambda: deque(maxlen=6))
    recent_score_deltas: deque[float] = field(default_factory=lambda: deque(maxlen=6))

    # Shadow posterior the opponent is likely to hold for our rat. This is a
    # rough proxy updated lazily per turn; used by search_policy for denial equity.
    opp_belief_peak_proxy: float = 0.0

    # Carpet planner output from the root. Consumed by the search for move ordering.
    planner_hint_key: Optional[Tuple[int, int, int]] = None

    # Latest search statistics (for logging / adaptive time manager).
    last_search_depth: int = 0
    last_search_nodes: int = 0
    last_root_top2_gap: float = 0.0
    last_root_branching: int = 0
