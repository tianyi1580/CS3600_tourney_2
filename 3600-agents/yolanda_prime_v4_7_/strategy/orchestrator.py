"""Per-turn orchestrator wiring every v3 subsystem together.

Pipeline (per turn):
    1. Apply search-channel belief updates.
    2. Run belief predict + update given sensor_data.
    3. Build BBState from engine Board.
    4. Compute territory map (Voronoi) + prime-potential field.
    5. Run carpet planner; get a preferred root move hint.
    6. Build info-foraging context (if entropy high).
    7. Build leaf evaluator bound to the prime-potential field + info ctx.
    8. Invoke iterative-deepening alpha-beta search with soft/hard deadlines.
    9. Compute ev_search, denial_equity via search_policy.
   10. Decide search-vs-move; return the final engine Move.
   11. Persist runtime state (snapshots, op-observation, search peaks).

On any exception the caller's fallback (first legal non-search move) kicks in.
"""
from __future__ import annotations

from collections import defaultdict, deque
import time
from typing import Callable, Optional, Tuple

import numpy as np

from game.board import Board
from game.enums import BOARD_SIZE
from game.move import Move

from ..infra.bitboard import (
    BBState,
    apply_move_key,
    generate_moves,
    key_to_move,
    move_immediate_points,
    zobrist_for_matrix,
)
from ..infra.runtime_state import RuntimeState
from ..infra.time_manager import ComplexitySignals, TimeManager
from ..tracking.belief import BeliefEngine
from ..tracking.opponent_observation import (
    OpponentCategory,
    infer_opponent_category,
    parse_search_tuple,
)
from .carpet_planner import plan_best_carpet_build
from .info_foraging import build_belief_info_fn, build_context
from .leaf_eval import build_leaf_eval
from .search.alphabeta import Searcher
from .search_policy import (
    decide_search,
    update_opp_peak_proxy,
)
from .territory import build_territory_lookup, compute_territory, prime_potential_array


class Orchestrator:
    """Stateful per-turn coordinator."""

    def __init__(self, weights: dict, *, enable_debug: bool = False):
        self.weights = weights
        self.enable_debug = enable_debug
        self._zobrist = None
        self._pending_update: Optional[Tuple[float, float]] = None

    # ---------------- Belief plumbing ----------------
    def _apply_search_channels(self, board: Board, belief: BeliefEngine, runtime: RuntimeState) -> None:
        if board.player_search != runtime.last_player_search:
            loc, result = parse_search_tuple(board.player_search)
            belief.apply_search_feedback(loc, result, is_self=True)
            if result is True:
                runtime.use_single_step = False
            runtime.last_player_search = board.player_search

        if board.opponent_search != runtime.last_opponent_search:
            loc, result = parse_search_tuple(board.opponent_search)
            if result is True:
                belief.apply_search_feedback(loc, result, is_self=False)
                runtime.use_single_step = True
            elif result is False and loc is not None:
                runtime.opp_miss_cell = loc
            runtime.last_opponent_search = board.opponent_search

    def _predict_update_belief(
        self, belief: BeliefEngine, runtime: RuntimeState, sensor_data
    ) -> None:
        if isinstance(sensor_data, tuple) and len(sensor_data) == 2:
            noise, estimated_distance = sensor_data
            belief.predict(runtime.use_single_step, runtime.opp_miss_cell)
            runtime.use_single_step = False
            runtime.opp_miss_cell = None
            # Note: update() relies on board being the *current* board before our move.
            # We delegate the actual call outside because it needs the board reference.
            # The caller supplies the board and invokes belief.update separately.
            self._pending_update = (noise, estimated_distance)
        else:
            self._pending_update = None

    def _observe_opponent(self, board: Board, runtime: RuntimeState) -> None:
        """Maintain the opponent category buffer for adaptation hooks."""
        try:
            cat = infer_opponent_category(
                runtime.snapshot_at_our_turn_start,
                runtime.last_own_move,
                board,
            )
        except Exception:
            cat = None
        if cat is not None:
            runtime.observed_turns += 1
            runtime.opp_turn_buffer.append((cat, 0))

    def _cell_types(self, board: Board) -> np.ndarray:
        N = BOARD_SIZE * BOARD_SIZE
        arr = np.zeros(N, dtype=np.int32)
        for i in range(N):
            arr[i] = int(board.get_cell((i % BOARD_SIZE, i // BOARD_SIZE)))
        return arr

    def _get_adversarial_overrides(self, runtime: RuntimeState) -> dict:
        """Analyze opponent style from buffer and return weight overrides."""
        if len(runtime.opp_turn_buffer) < 4:
            return {}
        
        counts = defaultdict(int)
        for cat, _ in runtime.opp_turn_buffer:
            if cat is not None:
                counts[cat] += 1
        
        overrides = {}
        total = sum(counts.values())
        if total == 0:
            return {}

        # Sub-optimal bot detection (The George Filter):
        # If opponent does many PLAIN steps, they likely lack lookahead.
        # We should NOT waste points trying to "deny" their searches.
        if total >= 15 and counts[OpponentCategory.PLAIN] / total > 0.35:
            overrides["lambda_denial"] = 0.05
            # Also be more aggressive about point scoring since they are slow.
            overrides["alpha"] = float(self.weights.get("alpha", 1.0)) * 1.3

        # Carpet-heavy opponent? Increase threat penalty and territory weight.
        elif counts[OpponentCategory.CARPET] / total > 0.15:
            overrides["omega_threat"] = float(self.weights.get("omega_threat", 0.6)) * 1.5
            overrides["beta"] = float(self.weights.get("beta", 0.35)) * 1.2
        
        # Search-heavy opponent? Be more aggressive about scoring.
        elif counts[OpponentCategory.SEARCH] / total > 0.70:
            overrides["alpha"] = float(self.weights.get("alpha", 1.0)) * 1.2
            
        return overrides

    def _ensure_zobrist(self, transition_matrix):
        if self._zobrist is None:
            self._zobrist = zobrist_for_matrix(transition_matrix)
        return self._zobrist

    def _get_forecast_data(self, belief: BeliefEngine) -> np.ndarray:
        """Project the rat distribution 3 turns into the future."""
        T2 = belief.transition_matrix_2
        b = belief.belief.copy()
        # 3-step forecast (6 single-steps)
        for _ in range(3):
            b = b @ T2
        return b

    # ---------------- Main entrypoint ----------------
    def select_action(
        self,
        *,
        board: Board,
        belief: BeliefEngine,
        runtime: RuntimeState,
        sensor_data,
        time_left: Callable,
    ) -> Move:
        # 1. Belief bookkeeping.
        self._apply_search_channels(board, belief, runtime)
        self._predict_update_belief(belief, runtime, sensor_data)
        if self._pending_update:
            noise, dist = self._pending_update
            belief.update(noise, dist, board)
            self._pending_update = None

        # 2. Observe opponent's last move for adaptation bookkeeping.
        self._observe_opponent(board, runtime)

        # 3. Build bitboard state.
        state = BBState.from_board(board)
        zobrist = self._ensure_zobrist(belief.transition_matrix)
        # Initialize the incremental hash correctly at the root via full scan.
        from ..infra.bitboard import zobrist_hash
        object.__setattr__(state, "hash", zobrist_hash(state, zobrist))
        
        root_moves = generate_moves(state)

        # 4. Territory + prime-potential field.
        territory = compute_territory(state)
        prime_pot_field = prime_potential_array(state)
        # O(1) territory lookup improvement from v3.
        territory_lookup = build_territory_lookup(prime_pot_field)

        # 5. Carpet planner hint.
        plan = plan_best_carpet_build(state, territory)
        runtime.planner_hint_key = plan.first_move if plan.first_move is not None else None

        # 6. Info-foraging context (gated on entropy).
        cell_types = self._cell_types(board)
        info_ctx = build_context(
            belief.belief,
            belief.noise_lut(),
            cell_types,
            gate_threshold=float(self.weights.get("info_entropy_gate", 0.75)),
        )
        belief_info_fn = build_belief_info_fn(info_ctx)

        # 7. Leaf evaluator with adversarial overrides and forecast hotspots.
        adv_overrides = self._get_adversarial_overrides(runtime)
        forecast_data = self._get_forecast_data(belief)
        leaf_eval = build_leaf_eval(
            self.weights, 
            territory_lookup, 
            belief_info_fn, 
            overrides=adv_overrides,
            forecast_data=forecast_data
        )
        root_eval = float(leaf_eval.evaluate(state))

        # 8. Time allocation.
        signals = ComplexitySignals(
            root_branching=len(root_moves),
            top2_gap=runtime.last_root_top2_gap,
            contested_count=territory.contested_count,
            belief_peak=float(np.max(belief.belief)) if belief.belief is not None else 0.0,
            recovery_mode=runtime.last_recovery_mode,
        )
        try:
            remaining = float(time_left())
        except Exception:
            remaining = runtime.initial_total_budget
        complexity = TimeManager.complexity_multiplier(signals, self.weights)
        alloc, emergency = TimeManager.allocation(
            board, runtime, remaining, self.weights, complexity_mult=complexity
        )
        start = time.monotonic()
        deadlines = TimeManager.deadlines(start, alloc)

        # 9. Alpha-beta iterative deepening search.
        searcher = Searcher(zobrist, leaf_eval)
        if emergency:
            # Fast path: depth 1 only.
            soft_deadline = min(start + 0.05, start + max(0.0, remaining))
            hard_deadline = min(start + 0.08, start + max(0.0, remaining))
            result = searcher.iterative_deepening(
                state,
                soft_deadline=soft_deadline,
                hard_deadline=hard_deadline,
                max_depth=1,
                prime_pot_field=prime_pot_field,
                planner_hint=runtime.planner_hint_key,
                root_moves=root_moves,
            )
        else:
            result = searcher.iterative_deepening(
                state,
                soft_deadline=deadlines.soft,
                hard_deadline=deadlines.hard,
                max_depth=24,
                prime_pot_field=prime_pot_field,
                planner_hint=runtime.planner_hint_key,
                root_moves=root_moves,
            )

        # Persist search stats for the time manager on the next turn.
        runtime.last_search_depth = result.depth
        runtime.last_search_nodes = result.nodes
        runtime.last_root_top2_gap = result.top2_gap
        runtime.last_root_branching = result.branching

        best_move_key = result.best_move

        # 10. Search-vs-move decision.
        # Fixed search gate unit logic: compare incremental point yield.
        q_best_non_search = _incremental_move_ev(state, best_move_key, zobrist)
        ab_delta = float(result.score - root_eval) if best_move_key is not None else 0.0
        
        phase = TimeManager.phase(board.turn_count)
        score_delta = (
            board.player_worker.get_points() - board.opponent_worker.get_points()
        )
        lambda_denial = float(self.weights.get("lambda_denial", 0.9))

        decision = decide_search(
            belief=belief,
            board=board,
            ev_best_move=q_best_non_search,
            ev_best_move_non_search=q_best_non_search,
            lambda_denial=lambda_denial,
            opp_peak_proxy=runtime.opp_belief_peak_proxy,
            phase=phase,
            recovery_mode=runtime.last_recovery_mode,
            turns_left=int(board.player_worker.turns_left),
            score_delta=int(score_delta),
            weights=self.weights,
        )

        our_peak = float(np.max(belief.belief)) if belief.belief is not None else 0.0
        runtime.opp_belief_peak_proxy = update_opp_peak_proxy(
            runtime.opp_belief_peak_proxy, our_peak
        )
        runtime.last_search_confidence = decision.ev_search + lambda_denial * decision.denial_equity

        # 11. Update recovery mode for next turn based on belief clarity.
        if our_peak < 0.10:
            runtime.last_recovery_mode = "panic"
        elif our_peak < 0.25:
            runtime.last_recovery_mode = "cautious"
        else:
            runtime.last_recovery_mode = "neutral"

        if decision.fire and decision.target is not None:
            final_move = Move.search(decision.target)
        elif best_move_key is not None:
            final_move = key_to_move(best_move_key)
        else:
            # Absolute fallback.
            fallbacks = board.get_valid_moves(exclude_search=True)
            final_move = fallbacks[0] if fallbacks else Move.search((0, 0))

        # 11. Snapshot for next-turn opponent observation.
        try:
            runtime.snapshot_at_our_turn_start = board.get_copy()
        except Exception:
            runtime.snapshot_at_our_turn_start = None
        runtime.last_own_move = final_move
        runtime.plies_as_player += 1

        recent_mode = "search" if decision.fire else ("plan" if runtime.planner_hint_key is not None else "tree")
        runtime.recent_modes.append(recent_mode)
        runtime.recent_positions.append(board.player_worker.get_location())

        if self.enable_debug:
            print(
                f"[yp3 turn={board.turn_count}] depth={result.depth} nodes={result.nodes} "
                f"score={result.score:.2f} q_best={q_best_non_search:.2f} "
                f"alloc={alloc:.3f} complex={complexity:.2f} "
                f"move={final_move} reason={decision.reason}"
            )

        return final_move


def _incremental_move_ev(state: BBState, mv_key, keys: Optional[ZobristKeys] = None) -> float:
    """Expected incremental points from playing `mv_key` this turn.

    Returns the concrete point delta the engine grants (PRIME=1, CARPET=pts),
    *plus* a small lookahead bonus for PRIME moves that immediately unlock a
    valuable carpet-roll on the next ply. The bonus is bounded so the gate
    still prefers a locked-in carpet-now over a speculative prime-then-carpet.

    This is the correct unit for comparing against ``ev_search = 6·p_max − 2``
    in `search_policy.decide_search`."""
    if mv_key is None:
        return 0.0
    base = float(move_immediate_points(mv_key))
    # For PRIME, peek at the resulting state and see if a long carpet is
    # immediately available next ply. This is the v2 "q_best_non" adjustment.
    if mv_key[0] == 1:  # PRIME
        try:
            # We need keys for apply_move_key; if not provided (e.g. from tests),
            # this part might fail or need a dummy.
            if keys is None:
                return base
            child = apply_move_key(state, mv_key, keys)
            # After swap, `us` is the opponent, so flip back to inspect what
            # *we* (the prime-caster) could do had the swap not occurred. The
            # cheap/safe approximation is to simply look at primed-chain length
            # from our new worker cell in the state pre-swap. Re-derive that
            # from `child` by using `child.opp` (our worker after priming) and
            # `child.primed`.
            from ..infra.bitboard import NEIGHBOR, NUM_DIR, RAY_SEQ, CARPET_POINTS_LUT
            us_after = child.opp
            primed = child.primed
            other = 1 << child.us  # opponent
            best_follow = 0
            for d in range(NUM_DIR):
                seq = RAY_SEQ[us_after][d]
                klen = 0
                for cell in seq:
                    cbit = 1 << cell
                    if not (primed & cbit) or (cbit & other):
                        break
                    klen += 1
                if klen >= 2 and klen < len(CARPET_POINTS_LUT):
                    pts = CARPET_POINTS_LUT[klen]
                    if pts > best_follow:
                        best_follow = pts
            if best_follow >= 2:
                base += min(2.0, 0.15 * best_follow)
        except Exception:
            pass
    return base
