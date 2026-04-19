from __future__ import annotations

from dataclasses import dataclass
import time

from game.enums import CARPET_POINTS_TABLE, Direction, MoveType
from game.move import Move

from .bitboard_state import (
    BitboardState,
    abstract_successors,
    adjacent_primed_chain_length,
    direction_axis,
    index_to_loc,
    move_immediate_points,
    move_signature,
    shortest_turn_distances,
)
from .voronoi import VoronoiSnapshot


@dataclass(frozen=True, slots=True)
class SearchContext:
    snapshot: VoronoiSnapshot
    ownership_safe_w: float
    ownership_contested_w: float
    ownership_dead_w: float
    lane_steal_w: float
    foraging_axis_w: float
    belief_entropy: float
    preferred_axis: str | None
    allow_foraging: bool
    bb_eval_mobility_w: float = 0.35
    bb_eval_local_chain_w: float = 0.45
    bb_eval_trap_w: float = 0.55


class _SearchTimeout(Exception):
    pass


class BitboardSearch:
    """Iterative deepening alpha-beta search over the Yolanda6 shadow state."""

    def __init__(self, *, tt_max_entries: int = 100_000, max_depth: int = 6) -> None:
        self.tt_max_entries = tt_max_entries
        self.max_depth = max_depth
        self._deadline = 0.0
        self._nodes = 0
        self._context: SearchContext | None = None
        self._tt: dict[tuple, tuple[int, float]] = {}

    def rank_moves(
        self,
        state: BitboardState,
        candidates: list[Move],
        budget_s: float,
        context: SearchContext,
    ) -> tuple[Move | None, float, int, dict[str, float]]:
        if budget_s <= 0.0:
            return None, float("-inf"), 0, {"depth": 0.0, "nodes": 0.0}

        root_moves = [move for move in candidates if move.move_type != MoveType.SEARCH and state.is_legal_non_search_move(move)]
        if not root_moves:
            return None, float("-inf"), 0, {"depth": 0.0, "nodes": 0.0}

        self._deadline = time.perf_counter() + budget_s
        self._nodes = 0
        self._context = context
        self._tt.clear()

        baseline = self.evaluate(state, context)
        ordered = sorted(root_moves, key=lambda move: self._root_order_key(state, move, context), reverse=True)

        best_move: Move | None = None
        best_total = float("-inf")
        completed_depth = 0

        for depth in range(1, self.max_depth + 1):
            if time.perf_counter() >= self._deadline:
                break
            current_best_move: Move | None = None
            current_best_total = float("-inf")
            alpha = float("-inf")
            beta = float("inf")
            try:
                for move in ordered:
                    self._check_deadline()
                    token = state.apply_move(move)
                    if token is None:
                        continue
                    total = -self._negamax(state, depth - 1, -beta, -alpha)
                    state.restore(token)
                    if total > current_best_total:
                        current_best_total = total
                        current_best_move = move
                    if total > alpha:
                        alpha = total
            except _SearchTimeout:
                break

            if current_best_move is None:
                break
            best_move = current_best_move
            best_total = current_best_total
            completed_depth = depth
            ordered.sort(key=lambda move: move_signature(move) != move_signature(best_move))

        if best_move is None:
            return None, float("-inf"), completed_depth, {"depth": float(completed_depth), "nodes": float(self._nodes)}
        return best_move, best_total - baseline, completed_depth, {"depth": float(completed_depth), "nodes": float(self._nodes)}

    def _negamax(self, state: BitboardState, depth: int, alpha: float, beta: float) -> float:
        self._check_deadline()
        if depth <= 0 or state.player_turns_left <= 0 or state.opponent_turns_left <= 0:
            return self.evaluate(state, self._context)

        tt_key = (
            state.space_mask,
            state.primed_mask,
            state.carpet_mask,
            state.blocked_mask,
            state.player_idx,
            state.opponent_idx,
            state.player_points,
            state.opponent_points,
            state.player_turns_left,
            state.opponent_turns_left,
            depth,
        )
        cached = self._tt.get(tt_key)
        if cached is not None and cached[0] >= depth:
            return cached[1]

        moves = state.valid_non_search_moves()
        if not moves:
            return self.evaluate(state, self._context)

        moves.sort(key=lambda move: self._root_order_key(state, move, self._context), reverse=True)
        best = float("-inf")
        for move in moves:
            token = state.apply_move(move)
            if token is None:
                continue
            score = -self._negamax(state, depth - 1, -beta, -alpha)
            state.restore(token)
            if score > best:
                best = score
            if best > alpha:
                alpha = best
            if alpha >= beta:
                break

        if len(self._tt) >= self.tt_max_entries:
            self._tt.clear()
        self._tt[tt_key] = (depth, best)
        return best

    def _root_order_key(self, state: BitboardState, move: Move, context: SearchContext) -> float:
        immediate = move_immediate_points(move)
        destination = state.destination_idx(move)
        mobility = len(abstract_successors(state, destination, state.opponent_idx))
        lane_bonus = context.lane_steal_w * self._lane_steal_bonus(state, destination, move, context.snapshot)
        if move.move_type == MoveType.CARPET:
            immediate += 0.2 * float(CARPET_POINTS_TABLE[min(move.roll_length, 7)])
        foraging_bonus = 0.0
        if context.allow_foraging and move.move_type in (MoveType.PLAIN, MoveType.PRIME):
            if direction_axis(move.direction) == context.preferred_axis:
                foraging_bonus += context.foraging_axis_w
        return immediate + lane_bonus + 0.1 * mobility + foraging_bonus

    @staticmethod
    def _lane_steal_bonus(state: BitboardState, destination: int, move: Move, snapshot: VoronoiSnapshot) -> float:
        dest_loc = index_to_loc(destination)
        best = 0.0
        for entry in snapshot.entries:
            if entry.zone != "contested":
                continue
            entry_loc = index_to_loc(entry.entry_idx)
            if move.move_type in (MoveType.PLAIN, MoveType.PRIME):
                if _shares_axis(dest_loc, entry_loc, entry.direction):
                    best = max(best, 0.3 * entry.value + 0.05 * entry.landing_exits)
            elif move.move_type == MoveType.CARPET and entry.chain_len <= move.roll_length:
                best = max(best, 0.2 * entry.value + 0.1 * entry.landing_exits)
        return best

    def evaluate(self, state: BitboardState, context: SearchContext | None) -> float:
        if context is None:
            return float(state.player_points - state.opponent_points)

        player_dists = shortest_turn_distances(state, state.player_idx, state.opponent_idx)
        opp_dists = shortest_turn_distances(state, state.opponent_idx, state.player_idx)
        score_diff = float(state.player_points - state.opponent_points)
        mobility_diff = float(len(abstract_successors(state, state.player_idx, state.opponent_idx)) - len(abstract_successors(state, state.opponent_idx, state.player_idx)))
        local_chain_diff = self._local_chain_potential(state, state.player_idx, state.opponent_idx) - self._local_chain_potential(state, state.opponent_idx, state.player_idx)
        ownership_diff = self._ownership_value(state, player_dists, opp_dists, context)
        trap_diff = self._trap_risk(state, state.player_idx, state.opponent_idx) - self._trap_risk(state, state.opponent_idx, state.player_idx)
        return (
            score_diff
            + context.bb_eval_mobility_w * mobility_diff
            + context.bb_eval_local_chain_w * local_chain_diff
            + ownership_diff
            - context.bb_eval_trap_w * trap_diff
        )

    @staticmethod
    def _local_chain_potential(state: BitboardState, idx: int, other_idx: int) -> float:
        best = 0.0
        for direction in Direction:
            chain_len = adjacent_primed_chain_length(state, idx, direction)
            if chain_len >= 2:
                best = max(best, 0.6 * float(CARPET_POINTS_TABLE[min(chain_len, 7)]))
        best += 0.08 * float(len(abstract_successors(state, idx, other_idx)))
        return best

    @staticmethod
    def _ownership_value(
        state: BitboardState,
        player_dists: list[int],
        opp_dists: list[int],
        context: SearchContext,
    ) -> float:
        ours = 0.0
        opp = 0.0
        for entry in context.snapshot.entries:
            pd = player_dists[entry.entry_idx]
            od = opp_dists[entry.entry_idx]
            if pd >= 0:
                axis_bonus = 0.25 if _shares_axis(index_to_loc(state.player_idx), index_to_loc(entry.entry_idx), entry.direction) else 0.0
                scale = _zone_scale(entry.zone, context)
                ours = max(ours, scale * (entry.value / (1.0 + pd) + axis_bonus + 0.08 * entry.landing_exits))
            if od >= 0:
                axis_bonus = 0.25 if _shares_axis(index_to_loc(state.opponent_idx), index_to_loc(entry.entry_idx), entry.direction) else 0.0
                scale = _zone_scale(entry.zone, context)
                opp = max(opp, scale * (entry.value / (1.0 + od) + axis_bonus + 0.08 * entry.landing_exits))
        return ours - opp

    @staticmethod
    def _trap_risk(state: BitboardState, idx: int, other_idx: int) -> float:
        exits = len(abstract_successors(state, idx, other_idx))
        if exits >= 3:
            return 0.0
        if exits == 2:
            return 0.4
        if exits == 1:
            return 1.2
        return 2.0

    def _check_deadline(self) -> None:
        self._nodes += 1
        if (self._nodes & 63) == 0 and time.perf_counter() >= self._deadline:
            raise _SearchTimeout


def _zone_scale(zone: str, context: SearchContext) -> float:
    if zone == "safe":
        return context.ownership_safe_w
    if zone == "contested":
        return context.ownership_contested_w
    return context.ownership_dead_w


def _shares_axis(loc_a: tuple[int, int], loc_b: tuple[int, int], direction: Direction) -> bool:
    if direction in (Direction.LEFT, Direction.RIGHT):
        return loc_a[1] == loc_b[1]
    return loc_a[0] == loc_b[0]
