"""Carpet-only quiescence search.

When the main search hits depth 0, we continue searching CARPET moves (with
roll_length ≥ 2) to avoid the horizon effect where a depth-N search misses a
large carpet-now-vs-next-turn trade. Primes and plain moves are *not* extended
(they don't change the score meaningfully without enabling a carpet).

Stand-pat: we evaluate the current position. A carpet move must raise that."""
from __future__ import annotations

from typing import Callable

from ...infra.bitboard import BBState, MoveKey, apply_move_key, generate_moves


EvalFn = Callable[[BBState], float]
TimeCheckFn = Callable[[], bool]


def quiesce(
    state: BBState,
    alpha: float,
    beta: float,
    evaluate: EvalFn,
    *,
    time_up: TimeCheckFn,
    depth_cap: int = 6,
) -> float:
    """Standard carpet-only quiescence search from the side-to-move viewpoint.

    Returns a score in the side-to-move frame (positive = side to move is
    winning). The caller negates across plies."""
    stand_pat = evaluate(state)
    if stand_pat >= beta:
        return beta
    if stand_pat > alpha:
        alpha = stand_pat
    if depth_cap <= 0 or time_up():
        return alpha
    if state.us_turns <= 0:
        return alpha

    # Only consider CARPET moves with roll_length >= 2 (the rewarding ones).
    moves = [mv for mv in generate_moves(state) if mv[0] == 2 and mv[2] >= 2]
    if not moves:
        return alpha

    # Sort by carpet roll length desc (higher points first).
    moves.sort(key=lambda m: -m[2])

    for mv in moves:
        child = apply_move_key(state, mv)
        score = -quiesce(
            child,
            -beta,
            -alpha,
            evaluate,
            time_up=time_up,
            depth_cap=depth_cap - 1,
        )
        if score >= beta:
            return beta
        if score > alpha:
            alpha = score
    return alpha
