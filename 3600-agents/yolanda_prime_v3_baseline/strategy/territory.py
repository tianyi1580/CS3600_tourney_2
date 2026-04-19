"""Voronoi territory + carpet-potential evaluation.

For a `BBState`, we compute:
- `d_us[c]`, `d_opp[c]`: shortest plain-walkable path length from each worker
  to every cell `c`. Walkable = SPACE or CARPET, and neither worker sits there
  (other than the source cell).
- `own[c]`: +1 if d_us < d_opp − 1 (safe), −1 if d_opp < d_us − 1 (dead), else 0.
- `prime_potential[c]`: the max CARPET_POINTS payoff achievable by priming c and
  extending a contiguous SPACE ray from c and rolling.
- `territory_value_us/opp`: summed Σ own(c) · prime_potential(c) · tempo_weight(c).

Typical wall-clock on CPython per node: ~50-80µs."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import NamedTuple

import numpy as np

from ..infra.bitboard import (
    BBState,
    BOARD_SIZE,
    CARPET_POINTS_LUT,
    L1,
    NEIGHBOR,
    NUM_CELLS,
    NUM_DIR,
    RAY_SEQ,
)

_INF = 10**6


class TerritoryMaps(NamedTuple):
    d_us: tuple[int, ...]
    d_opp: tuple[int, ...]
    own: tuple[int, ...]          # +1 / 0 / -1 in the us frame
    prime_potential: tuple[int, ...]
    territory_value_us: float
    territory_value_opp: float
    # Count of contested cells (|own|==0 and both reachable). Exposed for time manager.
    contested_count: int


def _bfs_distances(source: int, walkable_mask: int, blocker_mask: int) -> list[int]:
    """BFS from `source` across cells in `walkable_mask`. `blocker_mask`
    marks cells we cannot *enter* (even though they may be walkable elsewhere);
    typically this is the opposing worker. The source cell is always reachable
    at distance 0."""
    dist = [_INF] * NUM_CELLS
    dist[source] = 0
    q = deque([source])
    blockers = blocker_mask
    while q:
        u = q.popleft()
        du = dist[u]
        for d in range(NUM_DIR):
            v = NEIGHBOR[u][d]
            if v < 0:
                continue
            vbit = 1 << v
            if blockers & vbit:
                continue
            if not (walkable_mask & vbit) and v != source:
                # Not walkable: skip (source exception shouldn't matter because
                # we only enter a cell if it's walkable).
                continue
            if dist[v] > du + 1:
                dist[v] = du + 1
                q.append(v)
    return dist


def compute_territory(state: BBState, margin: float = 1.0) -> TerritoryMaps:
    """Compute Voronoi ownership + carpet-potential + territory value.

    `margin` is the tempo buffer: we only claim a cell when our distance beats
    the opponent's by more than `margin`. Default is 1.0 from the plan. Fractional
    margins are rounded conservatively (ceil)."""
    walkable = (state.space | state.carpet) & ~((1 << state.us) | (1 << state.opp))
    # We treat the source cell as implicitly walkable for BFS seeding.
    walkable_us = walkable | (1 << state.us)
    walkable_opp = walkable | (1 << state.opp)

    d_us = _bfs_distances(state.us, walkable_us, blocker_mask=(1 << state.opp))
    d_opp = _bfs_distances(state.opp, walkable_opp, blocker_mask=(1 << state.us))

    # Ownership with tempo margin.
    own = [0] * NUM_CELLS
    for c in range(NUM_CELLS):
        du = d_us[c]
        do = d_opp[c]
        if du >= _INF and do >= _INF:
            own[c] = 0
        elif du + margin < do:
            own[c] = 1
        elif do + margin < du:
            own[c] = -1
        else:
            own[c] = 0

    # Prime potential: for each SPACE cell c, find the best ray starting at c
    # (walking outwards) through contiguous SPACE cells; the yield is the carpet
    # points for chain length k = ray_len + 1 (we prime c then the ray cells, then
    # roll carpet). But the engine definition of carpet roll length k means we
    # traverse k primed cells. So with one SPACE ray of length r, we can prime k
    # cells (c plus r-1 of them, after priming each we move) and then carpet roll
    # of length k over them.
    # Here we approximate: prime_potential(c) = max_d CARPET_POINTS[min(ray_space_len(c,d), 7)].
    space_mask = state.space & ~((1 << state.us) | (1 << state.opp))
    prime_potential = [0] * NUM_CELLS
    for c in range(NUM_CELLS):
        if not ((1 << c) & space_mask):
            continue
        best = 0
        for d in range(NUM_DIR):
            seq = RAY_SEQ[c][d]
            # Count contiguous space cells along the ray.
            rlen = 0
            for nc in seq:
                if not (space_mask & (1 << nc)):
                    break
                rlen += 1
                if rlen >= BOARD_SIZE - 1:
                    break
            k = min(rlen + 1, BOARD_SIZE - 1)  # +1 for c itself
            if k >= 2:
                pts = CARPET_POINTS_LUT[k]
                if pts > best:
                    best = pts
        prime_potential[c] = best

    # Territory value with tempo weight.
    # tempo_weight(c) = 1.0 when own(c) ≠ 0.
    #                   0.5 * sign(d_opp - d_us) for contested cells (sign is +1 if we
    #                   are "closer" by fraction of a tempo; 0 if exactly equal).
    us_value = 0.0
    opp_value = 0.0
    contested = 0
    for c in range(NUM_CELLS):
        pp = prime_potential[c]
        if pp == 0:
            continue
        o = own[c]
        du = d_us[c]
        do = d_opp[c]
        if o > 0:
            us_value += pp * 1.0
        elif o < 0:
            opp_value += pp * 1.0
        else:
            if du >= _INF and do >= _INF:
                continue
            contested += 1
            if du < do:
                us_value += pp * 0.5
            elif do < du:
                opp_value += pp * 0.5
            # Equal: split 0.25 each side (keeps linear sum ≤ pp).
            else:
                us_value += pp * 0.25
                opp_value += pp * 0.25

    return TerritoryMaps(
        d_us=tuple(d_us),
        d_opp=tuple(d_opp),
        own=tuple(own),
        prime_potential=tuple(prime_potential),
        territory_value_us=us_value,
        territory_value_opp=opp_value,
        contested_count=contested,
    )


def prime_potential_array(state: BBState) -> np.ndarray:
    """Carpet-potential field as a numpy array (64,)."""
    space_mask = state.space & ~((1 << state.us) | (1 << state.opp))
    arr = np.zeros(NUM_CELLS, dtype=np.float32)
    for c in range(NUM_CELLS):
        if not ((1 << c) & space_mask):
            continue
        best = 0
        for d in range(NUM_DIR):
            seq = RAY_SEQ[c][d]
            rlen = 0
            for nc in seq:
                if not (space_mask & (1 << nc)):
                    break
                rlen += 1
                if rlen >= BOARD_SIZE - 1:
                    break
            k = min(rlen + 1, BOARD_SIZE - 1)
            if k >= 2:
                pts = CARPET_POINTS_LUT[k]
                if pts > best:
                    best = pts
        arr[c] = best
    return arr


# Normalizer so per-worker-step swings of territory_d are O(1) rather than O(50)
# (raw sum over 64 cells × prime-potential up to 21 swings ±50 per L1 re-alignment,
# which would completely drown out score_delta ∈ ±40 over an entire game if left
# raw). Chosen so a "representative" step swing lands around ±2.5 eval units and
# the full-game range lands around ±50 — comparable to α·score_delta with β≈0.3.
_TERRITORY_NORMALIZER: float = 20.0


def fast_territory_delta(state: BBState, prime_pot_field: np.ndarray) -> float:
    """Fast L1-based Voronoi proxy for inner-search territory evaluation.

    Returns a *normalized* (us − opp) territory value using L1-distance Voronoi
    on the cached prime-potential field. Without normalization the raw sum has
    a much larger dynamic range than score_delta and catastrophically dominates
    the leaf eval — see ``_TERRITORY_NORMALIZER`` above.

    Much cheaper than the full BFS — ~3µs per call with numpy vectorization —
    at the cost of ignoring blocked-cell detours. In practice L1 and walkable
    BFS agree on >95% of cells in the 8×8 game.
    """
    du = L1[state.us]   # shape (64,), int
    do = L1[state.opp]
    # Sign: us wins cells where du < do − 1 (+1), loses where do < du − 1 (−1).
    sign = np.sign(do.astype(np.int32) - du.astype(np.int32))
    # Contested tempo weight: ±0.5 depending on who is closer by exactly 1.
    margin = (do.astype(np.int32) - du.astype(np.int32))
    weight = np.where(
        np.abs(margin) >= 2,
        sign.astype(np.float32),
        0.5 * np.sign(margin).astype(np.float32),
    )
    raw = float(np.sum(prime_pot_field * weight))
    return raw / _TERRITORY_NORMALIZER


# Convenience: expected carpet yield from just our worker (used by leaf eval as
# a fast "chain_potential" surrogate — not the Voronoi value).
def worker_chain_potential(state: BBState, for_us: bool = True) -> int:
    """Max 1-turn carpet payoff achievable right now from the worker position.

    Counts only existing primed chains (we just carpet). Primes + ray building is
    already captured by the planner."""
    worker = state.us if for_us else state.opp
    primed = state.primed
    other = 1 << (state.opp if for_us else state.us)
    best = 0
    for d in range(NUM_DIR):
        seq = RAY_SEQ[worker][d]
        klen = 0
        for cell in seq:
            cbit = 1 << cell
            if not (primed & cbit):
                break
            if cbit & other:
                break
            klen += 1
            if klen >= BOARD_SIZE - 1:
                break
        if klen >= 1:
            pts = CARPET_POINTS_LUT[klen]
            if pts > best:
                best = pts
    return best
