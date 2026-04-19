from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Optional, Tuple

from game.move import Move

from ..tracking.opponent_observation import OpponentCategory

OPPONENT_WINDOW = 24
BASE_A = 1.00
BASE_B = 0.45
BASE_C = 0.60
BASE_D = 0.35
BASE_F = 0.75


@dataclass
class RuntimeState:
    """Shared mutable policy state kept across turns."""

    constructor_budget_remaining: float = 0.0
    initial_total_budget: float = 240.0
    emergency_floor_total: float = 1.2

    use_single_step: bool = False
    opp_miss_cell: tuple[int, int] | None = None

    mu_ev: float = 0.0
    sigma_ev: float = 1.0
    mu_t: float = 0.0
    sigma_t: float = 1.0

    observed_turns: int = 0
    opp_turn_buffer: deque[tuple[OpponentCategory | None, int]] = field(
        default_factory=lambda: deque(maxlen=OPPONENT_WINDOW)
    )
    opp_search_attempts: int = 0
    opp_search_correct: int = 0
    behavior_entropy_norm: float = 0.0

    policy_base_a: float = BASE_A
    policy_base_c: float = BASE_C
    policy_base_d: float = BASE_D
    policy_base_f: float = BASE_F
    effective_a: float = BASE_A
    effective_c: float = BASE_C
    effective_d: float = BASE_D
    effective_f: float = BASE_F
    effective_b: float = BASE_B
    enable_opponent_model: bool = True
    build_fingerprint: str = ""
    weights_profile: str = "default"

    farmable_rat: bool = False
    rat_concentration: float = 0.0

    plies_as_player: int = 0
    snapshot_at_our_turn_start: Any = None
    last_own_move: Optional[Move] = None
    fallback_move: Optional[Move] = None
    fallback_turn: int = -1

    last_opponent_search: Tuple[object, object] = field(default_factory=lambda: (None, None))
    last_player_search: Tuple[object, object] = field(default_factory=lambda: (None, None))
    recent_positions: deque[tuple[int, int]] = field(default_factory=lambda: deque(maxlen=4))


__all__ = ["RuntimeState"]
