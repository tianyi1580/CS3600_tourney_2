"""Territory / Voronoi correctness tests."""
from __future__ import annotations

import pytest

from common import make_board
from game.enums import Direction

from yolanda_prime_v3.infra.bitboard import BBState, coord_to_idx
from yolanda_prime_v3.strategy.carpet_planner import plan_best_carpet_build
from yolanda_prime_v3.strategy.territory import (
    build_territory_lookup,
    compute_territory,
    fast_territory_delta,
    prime_potential_array,
)


def test_voronoi_symmetric_board():
    b = make_board()
    b.player_worker.position = (0, 0)
    b.opponent_worker.position = (7, 7)
    state = BBState.from_board(b)
    t = compute_territory(state)
    assert abs(t.territory_value_us - t.territory_value_opp) < 1e-6
    # Own[0,0] should be us; own[7,7] should be opp.
    assert t.own[coord_to_idx(0, 0)] == 1
    assert t.own[coord_to_idx(7, 7)] == -1


def test_voronoi_single_worker_dominates():
    """If opponent is in a corner and we are centered, we own most of the board."""
    b = make_board()
    b.player_worker.position = (3, 3)
    b.opponent_worker.position = (7, 7)
    state = BBState.from_board(b)
    t = compute_territory(state)
    us_cells = sum(1 for o in t.own if o == 1)
    opp_cells = sum(1 for o in t.own if o == -1)
    assert us_cells > opp_cells


def test_prime_potential_matches_exact_straight_build_geometry():
    b = make_board()
    b.player_worker.position = (0, 0)
    b.opponent_worker.position = (7, 7)
    state = BBState.from_board(b)
    field = prime_potential_array(state)
    assert field[coord_to_idx(1, 1)] == 15
    assert field[coord_to_idx(2, 2)] == 10


def test_fast_territory_delta_reasonable():
    b = make_board()
    b.player_worker.position = (3, 3)
    b.opponent_worker.position = (7, 7)
    state = BBState.from_board(b)
    field = prime_potential_array(state)
    d = fast_territory_delta(state, field)
    # Us should have positive territory delta (we're more central).
    assert d > 0


def test_fast_territory_lookup_matches_fallback_field():
    b = make_board()
    b.player_worker.position = (2, 2)
    b.opponent_worker.position = (7, 7)
    state = BBState.from_board(b)
    field = prime_potential_array(state)
    lookup = build_territory_lookup(field)
    assert fast_territory_delta(state, lookup) == pytest.approx(
        fast_territory_delta(state, field)
    )


def test_planner_can_start_build_from_current_worker_square():
    b = make_board()
    b.player_worker.position = (0, 0)
    b.opponent_worker.position = (7, 7)
    state = BBState.from_board(b)
    plan = plan_best_carpet_build(state, compute_territory(state))
    assert plan.first_move in {
        (1, int(Direction.RIGHT), 0),
        (1, int(Direction.DOWN), 0),
    }
