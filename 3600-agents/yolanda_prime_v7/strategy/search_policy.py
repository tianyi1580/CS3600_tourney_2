"""Search-vs-move decision and opponent-denial equity.

The alpha-beta tree never expands SEARCH moves (they are stochastic and
decouple nicely). Instead, once per turn at the root, we compute:

  - ev_search       = 6·p_max − 2              (engine-defined search reward)
  - denial_equity   = 4·P(opp search hits this turn)   (value of hitting first)
  - ev_best_move    = root alpha-beta score at the deepest completed depth

Then:
  fire_search  iff  ev_search + λ_denial·denial_equity  >  ev_best_move + margin

The margin inherits v2's phase/lead/hysteresis logic because those scalars
have been tuned extensively and we don't want to destroy that information."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from game.board import Board

from ..infra.bitboard import L1
from ..tracking.belief import BeliefEngine


@dataclass
class SearchDecision:
    fire: bool
    target: Optional[tuple[int, int]]
    ev_search: float
    ev_best_move: float
    denial_equity: float
    reason: str


def compute_ev_search(belief: BeliefEngine) -> tuple[float, tuple[int, int], float]:
    """Return (ev, best_cell, p_max) for firing a search this turn."""
    topk = belief.topk(1)
    if not topk:
        return -2.0, (0, 0), 0.0
    (cell, p) = topk[0]
    return 6.0 * p - 2.0, cell, p


def estimate_opp_search_threat(
    belief: BeliefEngine,
    board: Board,
    opp_peak_proxy: float,
) -> tuple[float, tuple[int, int]]:
    """Rough denial-equity estimate: probability opponent hits a search this turn.

    The opponent also has a posterior with similar entropy (we don't see it,
    but both sides observe correlated sensor data). We proxy their peak as
    max(previous proxy, our_peak * 0.9 - 0.1) — symmetric information exposure."""
    topk = belief.topk(1)
    if not topk:
        return 0.0, (0, 0)
    (peak_cell, p_us) = topk[0]
    
    # Proxy peak: symmetric information exposure assumption.
    proxy_peak = max(opp_peak_proxy, max(0.0, 0.9 * p_us - 0.1))

    # L1 distance between opponent worker and our belief peak.
    ox, oy = board.opponent_worker.get_location()
    from game.enums import BOARD_SIZE
    opp_idx = oy * BOARD_SIZE + ox
    peak_idx = peak_cell[1] * BOARD_SIZE + peak_cell[0]
    dist = int(L1[opp_idx, peak_idx])

    # If opponent is far from the rat peak, their sensor diamond doesn't yet
    # localize it precisely; bleed the threat linearly.
    if dist > 6:
        proxy_peak *= 0.5
    elif dist > 3:
        proxy_peak *= 0.8

    return proxy_peak, peak_cell


def decide_search(
    *,
    belief: BeliefEngine,
    board: Board,
    ev_best_move: float,
    ev_best_move_non_search: float,
    lambda_denial: float,
    opp_peak_proxy: float,
    phase: str,
    recovery_mode: str,
    turns_left: int,
    score_delta: int,
    weights: dict,
    consecutive_misses: int = 0,
) -> SearchDecision:
    """Decide whether to fire a search this turn.

    v6.2: Adopts v5_1's proven search discipline — hard p_max floor at 0.45,
    denial equity nearly zeroed, minimal panic margin reduction. The layered-
    margin approach from v6.0/v6.1 caused compounding over-suppression.
    Additionally keeps the late-game deficit gate."""
    ev_search, cell, p_max = compute_ev_search(belief)
    threat_prob, peak_cell = estimate_opp_search_threat(
        belief,
        board,
        opp_peak_proxy,
    )
    denial_equity = 4.0 * threat_prob

    # Margin derived from v2 search gate.
    if phase == "opening":
        base_farm = float(weights.get("search_gate_base_farm", 0.22))
        slope_farm = float(weights.get("search_gate_slope_farm", 0.22))
        margin = base_farm + slope_farm * max(0, -score_delta) / 6.0
    elif phase == "late":
        base_nonfarm = float(weights.get("search_gate_base_nonfarm", 0.35))
        slope_nonfarm = float(weights.get("search_gate_slope_nonfarm", 0.5))
        margin = base_nonfarm + slope_nonfarm * max(0, score_delta) / 6.0
    else:
        # Mid-game margin blends the two.
        base_farm = float(weights.get("search_gate_base_farm", 0.22))
        slope_farm = float(weights.get("search_gate_slope_farm", 0.22))
        base_nonfarm = float(weights.get("search_gate_base_nonfarm", 0.35))
        slope_nonfarm = float(weights.get("search_gate_slope_nonfarm", 0.5))
        m1 = base_farm + slope_farm * max(0, -score_delta) / 6.0
        m2 = base_nonfarm + slope_nonfarm * max(0, score_delta) / 6.0
        margin = 0.5 * (m1 + m2)

    # v5_1-proven: Panic barely reduces margin (was -0.20 in v4_7, which
    # caused speculative searches; -0.05 is conservative enough).
    if recovery_mode == "panic":
        margin = max(0.0, margin - 0.05)
    elif recovery_mode == "cautious":
        margin += 0.2

    # v6: Late-game deficit gate — when behind with few turns, only search
    # with very strong belief (scoring moves are more reliable).
    if turns_left < 8 and score_delta < -5:
        margin += 0.5

    # v7: Search Hysteresis — if we've missed multiple times consecutively,
    # the belief map is likely stale or miscalibrated. Tighten margin.
    if consecutive_misses >= 2:
        margin += 0.15 * consecutive_misses

    # Endgame: denial moot on final turn.
    if turns_left <= 1:
        denial_equity = 0.0

    # v5_1-proven: Nearly zero denial equity in the fire decision.
    # Focus on our own hit probability rather than panic-searching to deny.
    fire = (ev_search + 0.02 * denial_equity) > (ev_best_move_non_search + margin)

    # v5_1-proven: Hard p_max floor at 0.45 — don't gamble on low probability.
    # This single gate eliminated more bad searches than any margin tuning.
    if p_max < 0.45:
        fire = False

    reason = (
        f"ev_search={ev_search:.2f} ev_best={ev_best_move_non_search:.2f} "
        f"denial={denial_equity:.2f} λ={lambda_denial:.2f} margin={margin:.2f} "
        f"p_max={p_max:.3f} phase={phase} recovery={recovery_mode}"
    )
    return SearchDecision(
        fire=fire,
        target=cell,
        ev_search=ev_search,
        ev_best_move=ev_best_move_non_search,
        denial_equity=denial_equity,
        reason=reason,
    )


def endgame_search_pwin(
    belief: BeliefEngine,
    turns_left: int,
    *,
    max_horizon: int = 5,
) -> float:
    """Rough probability we hit the rat at least once in the remaining `turns_left` turns.

    We estimate 1 - prod_{i=1..T} (1 - P(guess hits at turn i)), where each
    turn's hit probability is approximated as the peak belief after i-1
    two-step belief updates. This is a coarse but cheap proxy — extended to
    5 turns per the plan.

    Returns 0.0 if the rat is always distant / diffuse."""
    if turns_left <= 0:
        return 0.0

    horizon = min(turns_left, max_horizon)
    T2 = belief.transition_matrix_2
    b = belief.belief.copy()
    p_miss = 1.0
    for _ in range(horizon):
        p_hit = float(np.max(b))
        p_miss *= max(0.0, 1.0 - p_hit)
        b = b @ T2
        s = b.sum()
        if s > 0:
            b = b / s
    return 1.0 - p_miss


def update_opp_peak_proxy(prev: float, our_peak: float) -> float:
    """Update opponent's shadow-HMM peak proxy based on our current peak.

    Symmetric information exposure assumption: after each turn, the opp's
    posterior peak is roughly our peak minus some noise margin, lower-bounded
    by the previous frame's estimate (so it decays slowly)."""
    estimate = max(0.0, 0.9 * our_peak - 0.05)
    # Exponential smoothing to avoid ping-ponging.
    return 0.7 * prev + 0.3 * estimate
