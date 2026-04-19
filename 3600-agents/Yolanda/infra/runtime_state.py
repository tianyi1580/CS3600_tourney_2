from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Optional, Tuple

from game.move import Move

from ..strategy import adaptation
from ..tracking.opponent_observation import OpponentCategory


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

    # --- M3 opponent profile (v4 RuntimeState contract) ---
    observed_turns: int = 0
    """Count of opponent turns we successfully classified (>= MIN_OBSERVED_TURNS for adaptation)."""

    opp_turn_buffer: deque[tuple[OpponentCategory | None, int]] = field(
        default_factory=lambda: deque(maxlen=adaptation.OPPONENT_WINDOW)
    )
    """(category or None if unknown, opponent non-search mobility at observation time)."""

    opp_search_attempts: int = 0
    opp_search_correct: int = 0

    behavior_entropy_norm: float = 0.0

    policy_base_a: float = adaptation.BASE_A
    policy_base_c: float = adaptation.BASE_C
    policy_base_d: float = adaptation.BASE_D
    policy_base_f: float = adaptation.BASE_F

    effective_a: float = adaptation.BASE_A
    effective_c: float = adaptation.BASE_C
    effective_d: float = adaptation.BASE_D
    effective_f: float = adaptation.BASE_F
    effective_b: float = adaptation.BASE_B
    enable_opponent_model: bool = True
    enable_adaptive_margin: bool = True
    build_fingerprint: str = ""

    # T-matrix farmability check (§12 of movement strategy doc)
    farmable_rat: bool = False
    """Set True if max(b_reset) > 0.25, indicating highly concentrated stationary dist."""
    rat_concentration: float = 0.0
    """max(b_reset) — peak probability in the rat's stationary distribution."""

    plies_as_player: int = 0

    snapshot_at_our_turn_start: Any = None  # Board | None; avoid circular import
    last_own_move: Optional[Move] = None

    fallback_move: Optional[Move] = None
    fallback_turn: int = -1

    last_opponent_search: Tuple[object, object] = field(default_factory=lambda: (None, None))
    last_player_search: Tuple[object, object] = field(default_factory=lambda: (None, None))
