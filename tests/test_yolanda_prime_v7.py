from __future__ import annotations

import json
from unittest.mock import patch

from common import identity_transition, make_board
from game.enums import Cell, Direction, Noise

from yolanda_prime_v7.agent import PlayerAgent
from yolanda_prime_v7.infra.bitboard import BBState, generate_moves, zobrist_for_matrix, zobrist_hash
from yolanda_prime_v7.infra.runtime_state import RuntimeState
from yolanda_prime_v7.infra.weights import DEFAULTS
from yolanda_prime_v7.strategy.orchestrator import Orchestrator, _apply_root_guardrail, _incremental_move_ev
from yolanda_prime_v7.strategy.search.alphabeta import RootCandidate, SearchResult
from yolanda_prime_v7.strategy.search_policy import SearchDecision, decide_search
from yolanda_prime_v7.tracking.belief import BeliefEngine
from yolanda_prime_v7.tracking.opponent_observation import OpponentCategory


def test_lambda_denial_changes_search_decision() -> None:
    board = make_board()
    belief = BeliefEngine(identity_transition())
    belief.belief[:] = 0.0
    belief.belief[0] = 0.4

    with patch(
        "yolanda_prime_v7.strategy.search_policy.estimate_opp_search_threat",
        return_value=(1.0, (0, 0)),
    ):
        low = decide_search(
            belief=belief,
            board=board,
            ev_best_move=1.3,
            ev_best_move_non_search=1.3,
            lambda_denial=0.0,
            opp_peak_proxy=0.0,
            phase="opening",
            recovery_mode="neutral",
            turns_left=10,
            score_delta=0,
            weights=DEFAULTS,
        )
        high = decide_search(
            belief=belief,
            board=board,
            ev_best_move=1.3,
            ev_best_move_non_search=1.3,
            lambda_denial=0.4,
            opp_peak_proxy=0.0,
            phase="opening",
            recovery_mode="neutral",
            turns_left=10,
            score_delta=0,
            weights=DEFAULTS,
        )

    assert not low.fire
    assert high.fire


def test_george_filter_override_reaches_search_policy_after_fifteen_plain_turns() -> None:
    board = make_board()
    belief = BeliefEngine(identity_transition())
    runtime = RuntimeState()
    runtime.opp_turn_buffer.extend([(OpponentCategory.PLAIN, 0)] * 15)
    orchestrator = Orchestrator(weights=DEFAULTS)

    root_move = generate_moves(BBState.from_board(board))[0]
    captured: dict[str, object] = {}

    def _capture_decide_search(**kwargs):
        captured.update(kwargs)
        return SearchDecision(
            fire=False,
            target=None,
            ev_search=-2.0,
            ev_best_move=0.0,
            denial_equity=0.0,
            reason="test",
        )

    with patch(
        "yolanda_prime_v7.strategy.orchestrator.decide_search",
        side_effect=_capture_decide_search,
    ), patch(
        "yolanda_prime_v7.strategy.orchestrator.Searcher.iterative_deepening",
        return_value=SearchResult(
            best_move=root_move,
            score=0.0,
            depth=1,
            nodes=1,
            top2_gap=0.0,
            branching=1,
            root_candidates=[RootCandidate(move=root_move, score=0.0)],
        ),
    ):
        orchestrator.select_action(
            board=board,
            belief=belief,
            runtime=runtime,
            sensor_data=(Noise.SQUEAK, 4),
            time_left=lambda: 120.0,
        )

    assert RuntimeState().opp_turn_buffer.maxlen == 24
    assert captured["lambda_denial"] == 0.05
    assert captured["weights"]["lambda_denial"] == 0.05


def test_prime_followup_bonus_is_capped() -> None:
    board = make_board()
    board.player_worker.position = (1, 2)
    board.opponent_worker.position = (7, 7)
    for x in range(3, 8):
        board.set_cell((x, 2), Cell.PRIMED)

    state = BBState.from_board(board)
    keys = zobrist_for_matrix(identity_transition())
    object.__setattr__(state, "hash", zobrist_hash(state, keys))

    value = _incremental_move_ev(state, (1, int(Direction.RIGHT), 0), keys)
    assert value == 2.5


def test_root_guardrail_rejects_dominated_k1_carpet_and_preserves_proven_one() -> None:
    k1 = (2, int(Direction.RIGHT), 1)
    prime = (1, int(Direction.UP), 0)

    rejected = SearchResult(
        best_move=k1,
        score=4.8,
        root_candidates=[
            RootCandidate(move=k1, score=4.8),
            RootCandidate(move=prime, score=4.2),
        ],
    )
    preserved = SearchResult(
        best_move=k1,
        score=5.4,
        root_candidates=[
            RootCandidate(move=k1, score=5.4),
            RootCandidate(move=prime, score=4.3),
        ],
    )

    assert _apply_root_guardrail(rejected) == prime
    assert _apply_root_guardrail(preserved) == k1


def test_v7_identity_and_env_hooks_use_yp7_not_yp4() -> None:
    board = make_board(time_to_play=240)
    with patch.dict(
        "os.environ",
        {
            "YP4_WEIGHTS_JSON": json.dumps({"alpha": 0.25}),
            "YP7_WEIGHTS_JSON": json.dumps({"alpha": 1.7}),
        },
        clear=False,
    ):
        agent = PlayerAgent(board, identity_transition(), time_left=lambda: 20.0)

    assert agent.weights["alpha"] == 1.7
    assert agent.runtime_state.weights_profile == "env"
    assert agent.commentate().startswith("yolanda_prime_v7:")
