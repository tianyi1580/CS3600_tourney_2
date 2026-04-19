"""Multi-turn chained-carpet planner.

At the root, the orchestrator asks the planner: given the current bitboard and
the Voronoi map, what's the best chained-carpet plan I can execute in the safe
subregion, and what first move does that plan imply?

We enumerate straight-ray builds (k primes followed by one carpet roll) from
every worker-reachable cell, and bounded elbow-chain builds that share one
axis turn (cheap DP), ranked by expected points per tempo."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Optional

from ..infra.bitboard import (
    BBState,
    BOARD_SIZE,
    CARPET_POINTS_LUT,
    NEIGHBOR,
    NUM_CELLS,
    NUM_DIR,
    RAY_SEQ,
)
from .territory import TerritoryMaps

# Reverse direction lookup (UP<->DOWN, LEFT<->RIGHT).
_REV_DIR = (2, 3, 0, 1)


@dataclass(frozen=True)
class CarpetPlan:
    """Result of the planner: a preferred first-move key and an expected value."""

    first_move: Optional[tuple[int, int, int]]
    expected_points: float
    description: str = ""


def _reachable_cells(state: BBState, max_steps: int = 6) -> dict[int, int]:
    """BFS from our worker; return dict(cell_idx -> steps) up to max_steps.
    Walkable = SPACE or CARPET, blocked by opponent and primed cells."""
    walkable = (state.space | state.carpet) & ~((1 << state.opp))
    dist = {state.us: 0}
    q = deque([state.us])
    while q:
        u = q.popleft()
        du = dist[u]
        if du >= max_steps:
            continue
        for d in range(NUM_DIR):
            v = NEIGHBOR[u][d]
            if v < 0 or v in dist:
                continue
            if not (walkable & (1 << v)) and v != state.us:
                continue
            dist[v] = du + 1
            q.append(v)
    return dist


def _first_move_from_path(
    state: BBState, target: int, cell_to_prev: dict[int, tuple[int, int]]
) -> Optional[tuple[int, int, int]]:
    """Walk the BFS parent map back to produce the first step-move key toward target.

    Returns a PLAIN move key. Returns None if target == us (no move needed)."""
    if target == state.us:
        return None
    cur = target
    prev = cell_to_prev.get(cur)
    if prev is None:
        return None
    while prev[0] != state.us:
        cur = prev[0]
        prev = cell_to_prev.get(cur)
        if prev is None:
            return None
    # prev = (us, dir) means: from us go direction dir to cur.
    return (0, prev[1], 0)


def _reach_with_parents(state: BBState, max_steps: int = 6) -> tuple[dict[int, int], dict[int, tuple[int, int]]]:
    walkable = (state.space | state.carpet) & ~((1 << state.opp))
    dist = {state.us: 0}
    parent: dict[int, tuple[int, int]] = {}  # cell -> (prev_cell, step_dir)
    q = deque([state.us])
    while q:
        u = q.popleft()
        du = dist[u]
        if du >= max_steps:
            continue
        for d in range(NUM_DIR):
            v = NEIGHBOR[u][d]
            if v < 0 or v in dist:
                continue
            if not (walkable & (1 << v)) and v != state.us:
                continue
            dist[v] = du + 1
            parent[v] = (u, d)
            q.append(v)
    return dist, parent


def plan_best_carpet_build(
    state: BBState,
    territory: TerritoryMaps,
    *,
    safe_margin: int = 2,
    max_approach: int = 4,
) -> CarpetPlan:
    """Return the best straight-ray carpet build reachable from our worker.

    A "build" is:
      - Walk to a starting cell `s` in `approach` steps (plain moves).
      - Prime `k` cells along some direction d from `s`.
      - Roll carpet of length `k` in direction d.
    Total turns consumed: approach + k + 1. Total score: `k` prime points plus
    `CARPET_POINTS[k]`, where `k` is the number of forward SPACE cells available
    from the start cell before we carpet back over that trail.

    We require:
      - `s` must be on SPACE and owned by us in the Voronoi.
      - All k cells (including `s`) must be SPACE and own≥0 or opp's margin ≥ safe_margin.
      - Approach + k + 1 ≤ T_safe := d_opp(last_cell) − approach (conservative bound).
    """
    reach, parents = _reach_with_parents(state, max_steps=max_approach)
    space_mask = state.space & ~(1 << state.opp)
    own = territory.own
    d_opp = territory.d_opp

    best_plan = CarpetPlan(first_move=None, expected_points=0.0)

    for start_cell, approach in reach.items():
        if not (space_mask & (1 << start_cell)):
            continue
        if own[start_cell] < 0:
            continue

        # Try each direction; collect contiguous forward SPACE cells we could use
        # to build a carpet trail, then carpet back over that same path.
        for d in range(NUM_DIR):
            ray = RAY_SEQ[start_cell][d]
            forward_cells: list[int] = []
            for cell in ray:
                cbit = 1 << cell
                if not (space_mask & cbit):
                    break
                if own[cell] < 0 and (d_opp[cell] - territory.d_us[cell] <= safe_margin):
                    break
                forward_cells.append(cell)
                if len(forward_cells) >= BOARD_SIZE - 1:
                    break

            if len(forward_cells) < 2:
                continue

            for k in range(2, len(forward_cells) + 2):
                # Consumes approach + k (primes) + 1 (carpet) turns.
                cost_turns = approach + k + 1
                if cost_turns > state.us_turns:
                    break
                # Safety: last primed cell must still be reachable-faster-than-opp.
                last_cell = forward_cells[k - 2]
                if d_opp[last_cell] < cost_turns - 2:
                    break
                # Expected score: primes give +k, carpet gives points.
                carpet_pts = CARPET_POINTS_LUT[k] if k < len(CARPET_POINTS_LUT) else -10_000
                total = float(k + carpet_pts)
                if total <= 0:
                    continue
                # Discount by turn investment so longer plans need to pay off.
                per_tempo = total / max(1, cost_turns)
                ev = total * 0.5 + per_tempo * 0.5

                if ev > best_plan.expected_points:
                    # First move:
                    if approach == 0:
                        # We're already at start_cell; first move is PRIME d.
                        first_move = (1, d, 0)
                    else:
                        first_move = _first_move_from_path(state, start_cell, parents)
                    if first_move is None:
                        continue
                    best_plan = CarpetPlan(
                        first_move=first_move,
                        expected_points=ev,
                        description=(
                            f"straight k={k} dir={d} start={start_cell} approach={approach} total={total}"
                        ),
                    )

    # Elbow chain: start at `s`, prime k1 cells along d, then (with worker now
    # at the kth primed cell's successor) pivot to direction d' and prime k2
    # cells, then carpet-roll k2 only (the first leg stays as primes for later).
    # We approximate the yield as the best of (one-leg straight) + a bonus for
    # having the second leg set up. We include it only when T_safe is large
    # (≥5) so the search won't prefer an elbow to a clear straight line when
    # both are feasible.
    if state.us_turns >= 6:
        best_elbow = _plan_best_elbow(state, territory, reach, parents, safe_margin)
        if best_elbow.expected_points > best_plan.expected_points:
            best_plan = best_elbow

    return best_plan


def _plan_best_elbow(
    state: BBState,
    territory: TerritoryMaps,
    reach: dict[int, int],
    parents: dict[int, tuple[int, int]],
    safe_margin: int,
) -> CarpetPlan:
    """Two-leg chain: prime k1 along d, pivot at the end, prime k2 along d', carpet-roll k2.

    This is a coarse enumeration: we only consider pivots at the final primed
    cell of the first leg, and we assume the walker can continue because each
    step off a primed cell is a plain step."""
    space_mask = state.space & ~(1 << state.opp)
    own = territory.own
    d_opp = territory.d_opp
    best = CarpetPlan(first_move=None, expected_points=0.0)

    for start_cell, approach in reach.items():
        if not (space_mask & (1 << start_cell)):
            continue
        if own[start_cell] < 0:
            continue

        for d in range(NUM_DIR):
            ray = RAY_SEQ[start_cell][d]
            leg1: list[int] = []
            for cell in ray:
                cbit = 1 << cell
                if not (space_mask & cbit):
                    break
                if own[cell] < 0 and (d_opp[cell] - territory.d_us[cell] <= safe_margin):
                    break
                leg1.append(cell)
                if len(leg1) >= 4:  # Limit leg length in elbow search.
                    break
            if len(leg1) < 2:
                continue

            for k1 in range(1, len(leg1) + 1):
                # After `k1` forward prime steps from `start_cell`, the worker ends
                # on the `k1`th forward cell.
                pivot_cell = leg1[k1 - 1]
                if not (space_mask & (1 << pivot_cell)):
                    break

                for dp in range(NUM_DIR):
                    if dp == d or dp == _REV_DIR[d]:
                        continue
                    ray2 = RAY_SEQ[pivot_cell][dp]
                    leg2: list[int] = []
                    for cell in ray2:
                        cbit = 1 << cell
                        if not (space_mask & cbit):
                            break
                        if own[cell] < 0 and (d_opp[cell] - territory.d_us[cell] <= safe_margin):
                            break
                        leg2.append(cell)
                        if len(leg2) >= BOARD_SIZE - 1:
                            break
                    if len(leg2) < 2:
                        continue
                    for k2 in range(2, len(leg2) + 1):
                        cost_turns = approach + k1 + k2 + 1
                        if cost_turns > state.us_turns:
                            break
                        final_cell = leg2[k2 - 1]
                        if d_opp[final_cell] < cost_turns - 2:
                            break
                        carpet_pts = CARPET_POINTS_LUT[k2] if k2 < len(CARPET_POINTS_LUT) else -10_000
                        # Primes earned: k1 + k2. Carpet yield: k2.
                        total = float(k1 + k2 + carpet_pts)
                        if total <= 0:
                            continue
                        per_tempo = total / max(1, cost_turns)
                        ev = total * 0.45 + per_tempo * 0.55
                        if ev > best.expected_points:
                            if approach == 0:
                                first_move = (1, d, 0)
                            else:
                                first_move = _first_move_from_path(state, start_cell, parents)
                            if first_move is None:
                                continue
                            best = CarpetPlan(
                                first_move=first_move,
                                expected_points=ev,
                                description=(
                                    f"elbow k1={k1} d={d} k2={k2} dp={dp} total={total}"
                                ),
                            )
    return best
