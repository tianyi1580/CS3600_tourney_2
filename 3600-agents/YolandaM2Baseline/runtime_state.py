from dataclasses import dataclass, field
from typing import Optional, Tuple

from game.move import Move


@dataclass
class RuntimeState:
    """Shared mutable policy state kept across turns."""

    constructor_budget_remaining: float = 0.0
    initial_total_budget: float = 240.0
    emergency_floor_total: float = 1.2

    mu_ev: float = 0.0
    sigma_ev: float = 1.0
    mu_t: float = 0.0
    sigma_t: float = 1.0
    eps: float = 1e-6

    ev_count: int = 0
    t_count: int = 0
    ev_m2: float = 0.0
    t_m2: float = 0.0

    observed_turns: int = 0
    prime_heavy_turns: int = 0
    carpet_heavy_turns: int = 0
    search_heavy_turns: int = 0
    low_exit_entries: int = 0

    fallback_move: Optional[Move] = None
    fallback_turn: int = -1

    last_opponent_search: Tuple[object, object] = field(default_factory=lambda: (None, None))
    last_player_search: Tuple[object, object] = field(default_factory=lambda: (None, None))
