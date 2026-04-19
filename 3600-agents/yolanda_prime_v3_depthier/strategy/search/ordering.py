"""Move-ordering helpers for the alpha-beta search.

Given a `BBState` and a list of `MoveKey`s, return them in a priority order:
  1. TT best move (prepended externally if provided)
  2. Carpet moves sorted by raw carpet points desc (these are "captures")
  3. Primes ordered by forward primed-chain alignment
  4. Plain moves toward high prime-potential cells (hint bias)
  5. Killer move at this ply
  6. History heuristic

This is O(b log b) per node (b ≤ ~16)."""
from __future__ import annotations

from typing import Optional

import numpy as np

from ...infra.bitboard import (
    BBState,
    CARPET_POINTS_LUT,
    MoveKey,
    NEIGHBOR,
    NUM_DIR,
    RAY_SEQ,
)


_CARPET = 2
_PRIME = 1
_PLAIN = 0


class HistoryTable:
    """Simple history heuristic keyed by (from_idx, move_key)."""

    __slots__ = ("table", "max_val")

    def __init__(self):
        self.table: dict[tuple[int, MoveKey], int] = {}
        self.max_val = 1

    def bump(self, from_idx: int, key: MoveKey, depth: int) -> None:
        val = self.table.get((from_idx, key), 0) + depth * depth
        self.table[(from_idx, key)] = val
        if val > self.max_val:
            self.max_val = val

    def score(self, from_idx: int, key: MoveKey) -> int:
        return self.table.get((from_idx, key), 0)


class KillerTable:
    """Per-ply killer moves: up to 2 killers each ply."""

    __slots__ = ("rows",)

    def __init__(self, max_ply: int = 24):
        self.rows: list[list[Optional[MoveKey]]] = [[None, None] for _ in range(max_ply)]

    def put(self, ply: int, key: MoveKey) -> None:
        if ply < 0 or ply >= len(self.rows):
            return
        slot = self.rows[ply]
        if slot[0] == key:
            return
        slot[1] = slot[0]
        slot[0] = key

    def is_killer(self, ply: int, key: MoveKey) -> int:
        if ply < 0 or ply >= len(self.rows):
            return 0
        slot = self.rows[ply]
        if slot[0] == key:
            return 2
        if slot[1] == key:
            return 1
        return 0


def _prime_chain_ahead(state: BBState, from_idx: int, direction: int) -> int:
    """Length of contiguous primed chain ahead of the worker along the given direction."""
    primed = state.primed
    opp_bit = 1 << state.opp
    nxt = NEIGHBOR[from_idx][direction]
    if nxt < 0:
        return 0
    # The prime move doesn't place us on a primed cell; it primes our current
    # cell and moves us to `nxt`. So we want the primed chain from `nxt`.
    chain = 0
    cur = nxt
    # The `nxt` cell must be SPACE for the prime step to be legal, so we count
    # primed cells *beyond* it along the same direction.
    for cell in RAY_SEQ[nxt][direction]:
        cbit = 1 << cell
        if not (primed & cbit):
            break
        if cbit & opp_bit:
            break
        chain += 1
    return chain


def order_moves(
    state: BBState,
    moves: list[MoveKey],
    *,
    tt_best: Optional[MoveKey] = None,
    ply: int = 0,
    killers: Optional[KillerTable] = None,
    history: Optional[HistoryTable] = None,
    prime_pot_field: Optional[np.ndarray] = None,
    planner_hint: Optional[MoveKey] = None,
) -> list[MoveKey]:
    us_idx = state.us
    hist_max = history.max_val if history else 1

    def score(mv: MoveKey) -> int:
        mt, a, b = mv
        if tt_best is not None and mv == tt_best:
            return 1_000_000
        if planner_hint is not None and mv == planner_hint:
            return 800_000
        if mt == _CARPET:
            pts = CARPET_POINTS_LUT[b] if b < len(CARPET_POINTS_LUT) else 0
            # Short carpets (roll=1 is −1pt, roll=2 is just +2) are only marginal;
            # don't let them shadow a high-yield PRIME that unlocks a long chain.
            if pts <= 2:
                return 350_000 + pts * 1000
            return 500_000 + pts * 1000
        if mt == _PRIME:
            chain_ahead = _prime_chain_ahead(state, us_idx, a)
            # Score based on *next-turn* carpet-roll yield the prime will unlock
            # (the worker moves to `nbr`; from there carpet_len = chain_ahead + 1,
            # the priming cell counts towards the roll). If the priming yields a
            # long followup carpet (≥5pts) rank it above typical roll-2 carpets.
            follow_pts = 0
            if chain_ahead >= 0:
                roll_len = chain_ahead + 1
                if 0 <= roll_len < len(CARPET_POINTS_LUT):
                    follow_pts = CARPET_POINTS_LUT[roll_len]
            base_prime = 300_000 + max(0, follow_pts) * 2500
            if follow_pts >= 5:
                base_prime = max(base_prime, 520_000 + follow_pts * 1000)
            return base_prime
        # PLAIN: small demotion for stepping onto an existing carpet (usually
        # means we're wasting a turn — the cell is already claimed and can't be
        # re-primed). A SPACE neighbor is a "fresh" cell for priming next turn.
        base = 100_000
        if killers is not None:
            base += killers.is_killer(ply, mv) * 4000
        nbr = NEIGHBOR[us_idx][a]
        if nbr >= 0:
            nbr_bit = 1 << nbr
            if state.carpet & nbr_bit:
                base -= 30_000
        if prime_pot_field is not None and nbr >= 0:
            base += int(prime_pot_field[nbr] * 200)
        if history is not None:
            base += int(history.score(us_idx, mv) * 10000 / max(1, hist_max))
        return base

    return sorted(moves, key=score, reverse=True)
