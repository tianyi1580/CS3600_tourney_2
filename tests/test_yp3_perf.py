from __future__ import annotations

import os
import time

import pytest

from common import identity_transition, make_board
from game.enums import Noise

from yolanda_prime_v3.agent import PlayerAgent
from yolanda_prime_v3.infra.bitboard import BBState
from yolanda_prime_v3.infra.weights import DEFAULTS
from yolanda_prime_v3.strategy.leaf_eval import build_leaf_eval
from yolanda_prime_v3.strategy.territory import (
    build_territory_lookup,
    fast_territory_delta,
    prime_potential_array,
)


pytestmark = pytest.mark.skipif(
    os.getenv("YP3_RUN_PERF") != "1",
    reason="performance regressions are environment-sensitive; set YP3_RUN_PERF=1 to run.",
)


def test_territory_lookup_is_at_least_5x_faster_than_field_fallback():
    b = make_board()
    state = BBState.from_board(b)
    field = prime_potential_array(state)
    lookup = build_territory_lookup(field)

    start = time.perf_counter()
    for _ in range(100_000):
        fast_territory_delta(state, field)
    fallback_time = time.perf_counter() - start

    start = time.perf_counter()
    for _ in range(100_000):
        fast_territory_delta(state, lookup)
    lookup_time = time.perf_counter() - start

    assert fallback_time / lookup_time >= 5.0


def test_leaf_eval_with_lookup_is_materially_faster_than_field_fallback():
    b = make_board()
    state = BBState.from_board(b)
    field = prime_potential_array(state)
    lookup = build_territory_lookup(field)
    eval_field = build_leaf_eval(DEFAULTS, field)
    eval_lookup = build_leaf_eval(DEFAULTS, lookup)

    start = time.perf_counter()
    for _ in range(100_000):
        eval_field.evaluate(state)
    field_time = time.perf_counter() - start

    start = time.perf_counter()
    for _ in range(100_000):
        eval_lookup.evaluate(state)
    lookup_time = time.perf_counter() - start

    assert field_time / lookup_time >= 1.5


def test_opening_position_node_throughput_exceeds_80k_nps():
    board = make_board()
    agent = PlayerAgent(board, identity_transition(), time_left=lambda: 240.0)
    start = time.perf_counter()
    move = agent.play(board, (Noise.SQUEAK, 4), lambda: 240.0)
    elapsed = time.perf_counter() - start
    assert board.is_valid_move(move)

    nps = agent.runtime_state.last_search_nodes / max(elapsed, 1e-9)
    assert nps >= 80_000
