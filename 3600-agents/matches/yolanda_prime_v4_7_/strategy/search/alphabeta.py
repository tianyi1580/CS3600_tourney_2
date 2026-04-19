"""Iterative-deepening alpha-beta with PVS, aspiration windows, TT, LMR and
carpet-only quiescence."""
from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Callable, Optional

import numpy as np

from ...infra.bitboard import (
    BBState,
    MoveKey,
    ZobristKeys,
    _swap_sides_null,
    apply_move_key,
    generate_moves,
    zobrist_hash,
)
from .ordering import HistoryTable, KillerTable, order_moves
from .quiescence import quiesce


_TT_EXACT = 0
_TT_LOWER = 1
_TT_UPPER = 2
_INF = 10**8
# Windows / reductions:
_ASPIRATION_WINDOW = 50.0
_LMR_MIN_DEPTH = 3
_LMR_MIN_MOVE_IDX = 4
_MAX_DEPTH = 24


@dataclass(slots=True)
class TTEntry:
    depth: int
    flag: int
    value: float
    best_move: Optional[MoveKey]
    generation: int


@dataclass
class SearchResult:
    best_move: Optional[MoveKey]
    score: float
    pv: list[MoveKey] = field(default_factory=list)
    depth: int = 0
    nodes: int = 0
    top2_gap: float = 0.0
    branching: int = 0


class TimeUp(Exception):
    pass


class Searcher:
    """Iterative-deepening alpha-beta + PVS + TT + LMR + quiescence.

    The searcher is *stateless* across turns (TT/killers cleared between
    turns); the orchestrator instantiates a fresh one on each call. Zobrist
    keys are shared per-match."""

    def __init__(
        self,
        zobrist: ZobristKeys,
        evaluate: Callable[[BBState], float],
        *,
        tt_capacity: int = 80_000,
        max_ply: int = _MAX_DEPTH + 8,
    ):
        self.zobrist = zobrist
        self.evaluate = evaluate
        self.tt: "OrderedDict[int, TTEntry]" = OrderedDict()
        self.tt_capacity = tt_capacity
        self.killers = KillerTable(max_ply=max_ply)
        self.history = HistoryTable()
        self.nodes = 0
        self._soft_deadline = float("inf")
        self._hard_deadline = float("inf")
        self._time_check_every = 1023
        self.generation = 0
        self.prime_pot_field: Optional[np.ndarray] = None
        self.planner_hint: Optional[MoveKey] = None

    # ---------- TT helpers ----------
    def _tt_put(
        self,
        key: int,
        depth: int,
        flag: int,
        value: float,
        best_move: Optional[MoveKey],
    ) -> None:
        existing = self.tt.get(key)
        if existing is None:
            if len(self.tt) >= self.tt_capacity:
                self.tt.popitem(last=False)
            self.tt[key] = TTEntry(depth, flag, value, best_move, self.generation)
        else:
            # Replace if: same or deeper, or older generation.
            if existing.generation < self.generation or depth >= existing.depth:
                existing.depth = depth
                existing.flag = flag
                existing.value = value
                existing.best_move = best_move
                existing.generation = self.generation
                self.tt.move_to_end(key)

    def _tt_probe(self, key: int) -> Optional[TTEntry]:
        return self.tt.get(key)

    # ---------- Time management ----------
    def _time_up(self, hard: bool = False) -> bool:
        now = time.monotonic()
        if hard:
            return now >= self._hard_deadline
        return now >= self._soft_deadline

    # ---------- Search core ----------
    def iterative_deepening(
        self,
        root_state: BBState,
        *,
        soft_deadline: float,
        hard_deadline: float,
        max_depth: int = _MAX_DEPTH,
        prime_pot_field: Optional[np.ndarray] = None,
        planner_hint: Optional[MoveKey] = None,
        root_moves: Optional[list[MoveKey]] = None,
    ) -> SearchResult:
        self._soft_deadline = soft_deadline
        self._hard_deadline = hard_deadline
        self.prime_pot_field = prime_pot_field
        self.planner_hint = planner_hint
        self.nodes = 0
        self.generation += 1

        if root_moves is None:
            root_moves = generate_moves(root_state)
        else:
            root_moves = list(root_moves)
        if not root_moves:
            return SearchResult(best_move=None, score=self.evaluate(root_state), pv=[])

        best_move = root_moves[0]
        best_score = 0.0
        last_pv: list[MoveKey] = [best_move]
        depth_reached = 0
        prev_score: Optional[float] = None
        top2_gap = 0.0

        try:
            for depth in range(1, max_depth + 1):
                if time.monotonic() >= self._hard_deadline:
                    break

                if prev_score is None or depth < 4:
                    alpha, beta = -float(_INF), float(_INF)
                else:
                    alpha = prev_score - _ASPIRATION_WINDOW
                    beta = prev_score + _ASPIRATION_WINDOW

                while True:
                    try:
                        score, mv, pv, gap = self._search_root(
                            root_state,
                            depth,
                            alpha,
                            beta,
                            root_moves=root_moves,
                        )
                    except TimeUp:
                        raise
                    if score <= alpha:
                        alpha = -float(_INF)
                    elif score >= beta:
                        beta = float(_INF)
                    else:
                        best_score = score
                        best_move = mv if mv is not None else best_move
                        last_pv = pv if pv else [best_move]
                        depth_reached = depth
                        prev_score = score
                        top2_gap = gap
                        break

                # Between iterations, bail early if we're past the soft deadline.
                if time.monotonic() >= self._soft_deadline:
                    break
        except TimeUp:
            pass

        return SearchResult(
            best_move=best_move,
            score=best_score,
            pv=last_pv,
            depth=depth_reached,
            nodes=self.nodes,
            top2_gap=top2_gap,
            branching=len(root_moves),
        )

    def _search_root(
        self,
        state: BBState,
        depth: int,
        alpha: float,
        beta: float,
        *,
        root_moves: Optional[list[MoveKey]] = None,
    ) -> tuple[float, Optional[MoveKey], list[MoveKey], float]:
        key = state.hash
        tt_best = None
        ent = self._tt_probe(key)
        if ent is not None:
            tt_best = ent.best_move

        moves = list(root_moves) if root_moves is not None else generate_moves(state)
        moves = order_moves(
            state,
            moves,
            tt_best=tt_best,
            ply=0,
            killers=self.killers,
            history=self.history,
            prime_pot_field=self.prime_pot_field,
            planner_hint=self.planner_hint,
        )

        alpha_orig = alpha
        best_score = -float(_INF)
        best_move: Optional[MoveKey] = None
        best_pv: list[MoveKey] = []
        second_best = -float(_INF)
        failed_high = False

        for idx, mv in enumerate(moves):
            child = apply_move_key(state, mv, self.zobrist)
            if idx == 0:
                score, pv = self._negamax(child, depth - 1, -beta, -alpha, ply=1)
                score = -score
            else:
                score, pv = self._negamax(child, depth - 1, -alpha - 1, -alpha, ply=1)
                score = -score
                if alpha < score < beta:
                    score, pv = self._negamax(child, depth - 1, -beta, -alpha, ply=1)
                    score = -score

            if score > best_score:
                second_best = best_score
                best_score = score
                best_move = mv
                best_pv = [mv] + pv
            elif score > second_best:
                second_best = score

            if best_score > alpha:
                alpha = best_score
            if alpha >= beta:
                failed_high = True
                break

        # TT flag: LOWER on fail-high, UPPER on fail-low, else EXACT.
        if failed_high:
            flag = _TT_LOWER
        elif best_score <= alpha_orig:
            flag = _TT_UPPER
        else:
            flag = _TT_EXACT
        self._tt_put(key, depth, flag, best_score, best_move)

        gap = 0.0
        if second_best > -float(_INF):
            gap = best_score - second_best
        return best_score, best_move, best_pv, gap

    def _negamax(
        self, state: BBState, depth: int, alpha: float, beta: float, *, ply: int
    ) -> tuple[float, list[MoveKey]]:
        self.nodes += 1
        if self.nodes & self._time_check_every == 0:
            if self._time_up(hard=True):
                raise TimeUp()

        # Terminal / depth-0 leaf.
        if state.us_turns <= 0:
            # Our turns exhausted; but opponent may still play — from side-to-move
            # view (us == current mover), we can't move, so treat as leaf eval.
            return self.evaluate(state), []
        if depth <= 0:
            # Quiescence: extend with carpet-only moves.
            q = quiesce(
                state,
                alpha,
                beta,
                self.evaluate,
                keys=self.zobrist,
                time_up=lambda: self._time_up(hard=True),
            )
            return q, []

        key = state.hash
        alpha_orig = alpha

        # --- Null-Move Pruning (NMP) ---
        # If we are not in check (n/a here), have at least some depth, and
        # a stand-pat evaluation exceeds beta, we skip the move and see if the
        # score remains above beta.
        #
        # v4 FIX: Disable in endgame (turns_left <= 10) to avoid tactical blind spots.
        if depth >= 3 and ply > 0 and state.us_turns > 10:
            # Stand-pat check.
            static_eval = self.evaluate(state)
            if static_eval >= beta:
                # Reduced depth null-search.
                R = 2 if depth > 6 else 1
                null_child = _swap_sides_null(state, self.zobrist)
                # Null window search.
                score, _ = self._negamax(null_child, depth - 1 - R, -beta, -beta + 1, ply=ply + 1)
                score = -score
                if score >= beta:
                    return score, []

        tt_best: Optional[MoveKey] = None
        ent = self._tt_probe(key)
        if ent is not None and ent.depth >= depth:
            if ent.flag == _TT_EXACT:
                return ent.value, [ent.best_move] if ent.best_move else []
            if ent.flag == _TT_LOWER and ent.value > alpha:
                alpha = ent.value
            elif ent.flag == _TT_UPPER and ent.value < beta:
                beta = ent.value
            if alpha >= beta:
                return ent.value, [ent.best_move] if ent.best_move else []
            tt_best = ent.best_move
        elif ent is not None:
            tt_best = ent.best_move

        moves = generate_moves(state)
        if not moves:
            # No move available; evaluate stand-pat.
            return self.evaluate(state), []

        moves = order_moves(
            state,
            moves,
            tt_best=tt_best,
            ply=ply,
            killers=self.killers,
            history=self.history,
            prime_pot_field=self.prime_pot_field,
            planner_hint=self.planner_hint if ply == 0 else None,
        )

        best_score = -float(_INF)
        best_move: Optional[MoveKey] = None
        best_pv: list[MoveKey] = []

        for idx, mv in enumerate(moves):
            child = apply_move_key(state, mv, self.zobrist)

            # Late move reductions.
            reduce = 0
            if (
                depth >= _LMR_MIN_DEPTH
                and idx >= _LMR_MIN_MOVE_IDX
                and mv[0] != 2  # never reduce carpets (they are "captures")
                and mv != tt_best
            ):
                reduce = 1

            if idx == 0:
                score, pv = self._negamax(child, depth - 1, -beta, -alpha, ply=ply + 1)
                score = -score
            else:
                # Null-window; with potential LMR.
                score, pv = self._negamax(child, depth - 1 - reduce, -alpha - 1, -alpha, ply=ply + 1)
                score = -score
                if reduce and score > alpha:
                    score, pv = self._negamax(child, depth - 1, -alpha - 1, -alpha, ply=ply + 1)
                    score = -score
                if alpha < score < beta:
                    score, pv = self._negamax(child, depth - 1, -beta, -alpha, ply=ply + 1)
                    score = -score
        

            if score > best_score:
                best_score = score
                best_move = mv
                best_pv = [mv] + pv
            if score > alpha:
                alpha = score
            if alpha >= beta:
                if mv[0] != 2:
                    self.killers.put(ply, mv)
                    self.history.bump(state.us, mv, depth)
                break

        # TT store.
        flag = (
            _TT_UPPER if best_score <= alpha_orig else (_TT_EXACT if best_score < beta else _TT_LOWER)
        )
        self._tt_put(key, depth, flag, best_score, best_move)

        return best_score, best_pv
