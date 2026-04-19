from __future__ import annotations

from unittest.mock import patch

from common import identity_transition, make_board
from game.enums import Noise

from yolanda_prime_v3.infra.bitboard import BBState, generate_moves
from yolanda_prime_v3.infra.runtime_state import RuntimeState
from yolanda_prime_v3.infra.time_manager import TimeManager
from yolanda_prime_v3.infra.weights import DEFAULTS
from yolanda_prime_v3.strategy.orchestrator import Orchestrator
from yolanda_prime_v3.strategy.search.alphabeta import SearchResult
from yolanda_prime_v3.strategy.search_policy import SearchDecision
from yolanda_prime_v3.tracking.belief import BeliefEngine


def _run_turn_with_gap(prev_gap: float) -> tuple[object, float, int]:
    board = make_board()
    belief = BeliefEngine(identity_transition())
    runtime = RuntimeState()
    runtime.last_root_top2_gap = prev_gap
    orchestrator = Orchestrator(weights=DEFAULTS)

    root_moves = generate_moves(BBState.from_board(board))
    captured: dict[str, object] = {}
    original_complexity = TimeManager.complexity_multiplier.__func__

    def _capture_complexity(signals, weights):
        captured["signals"] = signals
        return original_complexity(TimeManager, signals, weights)

    def _capture_allocation(board, state, time_remaining, weights, *, complexity_mult):
        captured["complexity_mult"] = complexity_mult
        return 0.05, True

    with patch.object(TimeManager, "complexity_multiplier", side_effect=_capture_complexity), patch.object(
        TimeManager,
        "allocation",
        side_effect=_capture_allocation,
    ), patch(
        "yolanda_prime_v3.strategy.orchestrator.decide_search",
        return_value=SearchDecision(
            fire=False,
            target=None,
            ev_search=-2.0,
            ev_best_move=0.0,
            denial_equity=0.0,
            reason="test",
        ),
    ), patch(
        "yolanda_prime_v3.strategy.orchestrator.Searcher.iterative_deepening",
        return_value=SearchResult(
            best_move=root_moves[0],
            score=0.0,
            depth=1,
            nodes=1,
            top2_gap=0.25,
            branching=len(root_moves),
        ),
    ):
        orchestrator.select_action(
            board=board,
            belief=belief,
            runtime=runtime,
            sensor_data=(Noise.SQUEAK, 4),
            time_left=lambda: 120.0,
        )

    return captured["signals"], float(captured["complexity_mult"]), len(root_moves)


def test_orchestrator_uses_current_root_branching_before_search():
    signals, _complexity, branching = _run_turn_with_gap(prev_gap=0.0)
    assert signals.root_branching == branching


def test_previous_turn_top2_gap_feeds_next_turn_allocation():
    low_gap_signals, low_gap_complexity, _ = _run_turn_with_gap(prev_gap=0.1)
    high_gap_signals, high_gap_complexity, _ = _run_turn_with_gap(prev_gap=4.0)
    assert low_gap_signals.top2_gap == 0.1
    assert high_gap_signals.top2_gap == 4.0
    assert low_gap_complexity > high_gap_complexity
