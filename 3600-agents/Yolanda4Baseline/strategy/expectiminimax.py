"""Advanced Expectiminimax search engine for Yolanda4.

Implements a proper Minimax tree with:
  - MAX nodes for our turns, MIN nodes for opponent turns (alpha-beta pruned)
  - Depth-diffused rat belief for positional search-option valuation
  - Temporal discounting on chain accessibility
  - Root-level score-context modifiers for aggression/safety scaling
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING

import numpy as np

from game.board import Board
from game.enums import CARPET_POINTS_TABLE, Direction, MoveType, loc_after_direction
from game.move import Move
from .board_analysis import BoardAnalysis, BOARD_CELLS, INF, _index_to_loc, _NEIGHBORS_BY_INDEX

if TYPE_CHECKING:
    from .policy import PolicyEngine


_DIRECTIONS: tuple[Direction, ...] = (
    Direction.UP,
    Direction.DOWN,
    Direction.LEFT,
    Direction.RIGHT,
)


class _SearchTimeout(Exception):
    pass


class Expectiminimax:
    """Proper Minimax with alpha-beta pruning, rat-aware evaluation, and temporal discounting."""

    DEPTHS: tuple[int, ...] = range(2, 10, 1)

    def __init__(
        self,
        policy: PolicyEngine,
        root_analysis: BoardAnalysis | None = None,
        *,
        chain_potential_weight: float = 1.0,
        root_belief: np.ndarray | None = None,
        transition_matrix: np.ndarray | None = None,
        root_board: Board | None = None,
        eval_potential_w: float = 0.55,
        eval_chain_w: float = 0.60,
        eval_exit_w: float = 0.35,
        eval_entry_adv_w: float = 0.30,
        eval_trap_w: float = 0.80,
        eval_rat_w: float = 0.35,
        rat_nearby_w: float = 2.0,
        rat_peak_w: float = 3.0,
        rat_peak_thresh: float = 0.20,
    ) -> None:
        self.policy = policy
        self.root_analysis = root_analysis
        self.chain_potential_weight = chain_potential_weight
        self.root_board = root_board
        self.eval_potential_w = eval_potential_w
        self.eval_chain_w = eval_chain_w
        self.eval_exit_w = eval_exit_w
        self.eval_entry_adv_w = eval_entry_adv_w
        self.eval_trap_w = eval_trap_w
        self.eval_rat_w = eval_rat_w
        self.rat_nearby_w = rat_nearby_w
        self.rat_peak_w = rat_peak_w
        self.rat_peak_thresh = rat_peak_thresh

        self._deadline = 0.0
        self._nodes = 0
        self._tt: dict[tuple, float] = {}
        self._analysis_cache: dict[tuple, BoardAnalysis] = {}

        # --- Pre-compute depth-diffused beliefs (rat moves once per game turn) ---
        self._diffused_beliefs: dict[int, np.ndarray] = {}
        if root_belief is not None and transition_matrix is not None:
            T = np.asarray(transition_matrix, dtype=np.float64)
            self._diffused_beliefs[0] = root_belief.copy()
            current = root_belief.copy()
            for d in range(1, 6):
                current = current @ T
                s = current.sum()
                if s > 0:
                    current = current / s
                self._diffused_beliefs[d] = current.copy()

        # --- Pre-compute root score context (once, not per-leaf) ---
        self._aggression = 1.0
        self._safety = 1.0
        if root_board is not None:
            self._aggression, self._safety = self._score_context_modifier(root_board)

    # ------------------------------------------------------------------ #
    #  Public API                                                         #
    # ------------------------------------------------------------------ #

    def rank_moves(
        self,
        board: Board,
        candidates: list[Move],
        time_budget_s: float,
    ) -> tuple[Move | None, float, bool]:
        """Iterative-deepening minimax over *candidates* at the root."""
        if not candidates or time_budget_s <= 0.0:
            return None, float("-inf"), False

        start = time.perf_counter()
        self._deadline = start + time_budget_s
        self._nodes = 0
        self._tt.clear()
        self._analysis_cache.clear()

        ordered_root = self._ordered_moves(board, candidates)

        best_move: Move | None = None
        best_value = float("-inf")
        completed_depth2 = False

        for depth in self.DEPTHS:
            if time.perf_counter() - start >= time_budget_s * 0.9:
                break
            try:
                move_d, value_d = self._search_at_depth(board, ordered_root, depth)
            except _SearchTimeout:
                break
            if move_d is None:
                continue
            best_move = move_d
            best_value = value_d
            if depth >= 2:
                completed_depth2 = True

        return best_move, best_value, completed_depth2

    # ------------------------------------------------------------------ #
    #  Core Search                                                        #
    # ------------------------------------------------------------------ #

    def _search_at_depth(self, board: Board, root_moves: list[Move], depth: int) -> tuple[Move | None, float]:
        best_move: Move | None = None
        best_value = float("-inf")
        alpha = float("-inf")
        beta = float("inf")

        for mv in root_moves:
            self._check_deadline()
            nxt = self._transition(board, mv)
            if nxt is None:
                continue
            gain, board_next = nxt
            # After our move, it's opponent's turn (MIN node).
            val = gain + self._minimax(board_next, depth - 1, False, alpha - gain, beta - gain)
            if val > best_value or (
                val == best_value
                and best_move is not None
                and self.policy.move_sort_key(mv) < self.policy.move_sort_key(best_move)
            ):
                best_move = mv
                best_value = val
            alpha = max(alpha, best_value)
            if alpha >= beta:
                break

        return best_move, best_value

    def _minimax(self, board: Board, depth: int, maximizing: bool,
                 alpha: float, beta: float) -> float:
        """Recursive minimax with alpha-beta pruning."""
        self._check_deadline()

        if depth <= 0:
            return self._advanced_static_eval(board)

        cache_key = (self._board_key(board), maximizing, depth)
        cached = self._tt.get(cache_key)
        if cached is not None:
            return cached

        if maximizing:
            value = self._max_node(board, depth, alpha, beta)
        else:
            value = self._min_node(board, depth, alpha, beta)

        self._tt[cache_key] = value
        return value

    def _max_node(self, board: Board, depth: int, alpha: float, beta: float) -> float:
        """Our turn: MAX node with alpha-beta pruning."""
        moves = self._filtered_moves(board)
        if not moves:
            return self._advanced_static_eval(board)

        best = float("-inf")
        for mv in self._ordered_moves(board, moves):
            nxt = self._transition(board, mv)
            if nxt is None:
                continue
            gain, board_next = nxt
            val = gain + self._minimax(board_next, depth - 1, False, alpha - gain, beta - gain)
            best = max(best, val)
            alpha = max(alpha, best)
            if alpha >= beta:
                break  # Beta cutoff

        return best if best != float("-inf") else self._advanced_static_eval(board)

    def _min_node(self, board: Board, depth: int, alpha: float, beta: float) -> float:
        """Opponent's turn: MIN node with alpha-beta pruning.

        The opponent selects the move that MINIMIZES our evaluation.
        """
        board.reverse_perspective()
        try:
            moves = self._filtered_moves(board)
            if not moves:
                board.reverse_perspective()
                return self._advanced_static_eval(board)

            ordered = self._ordered_moves(board, moves)
            best = float("inf")

            for mv in ordered:
                nxt = self._transition(board, mv)
                if nxt is None:
                    continue
                gain, board_next = nxt
                board_next.reverse_perspective()

                # From our perspective: opponent's gain is our loss
                child_val = -gain + self._minimax(board_next, depth - 1, True, alpha + gain, beta + gain)
                best = min(best, child_val)
                beta = min(beta, best)
                if beta <= alpha:
                    break  # Alpha cutoff
        finally:
            board.reverse_perspective()

        return best if best != float("inf") else self._advanced_static_eval(board)

    # ------------------------------------------------------------------ #
    #  Move Filtering & Ordering                                          #
    # ------------------------------------------------------------------ #

    def _filtered_moves(self, board: Board) -> list[Move]:
        """Generate non-search moves, filtering out dead-ends and corridor traps."""
        move_meta: list[tuple[Move, bool]] = []
        non_corridor_exists = False

        for mv in board.get_valid_moves(exclude_search=True):
            if mv.move_type == MoveType.SEARCH:
                continue
            if mv.move_type == MoveType.CARPET and mv.roll_length <= 1:
                continue

            board_after = board.forecast_move(mv, check_ok=False)
            if board_after is None:
                continue

            dest = self.policy._destination(board, mv)
            exits = self.policy._count_plain_exits(board_after, dest)
            if exits <= 0:
                continue
            if mv.move_type == MoveType.PRIME and exits < 2:
                continue

            corridor = self.policy._is_corridor_trap_move(board, mv)
            move_meta.append((mv, corridor))
            if not corridor:
                non_corridor_exists = True

        result: list[Move] = []
        for mv, corridor in move_meta:
            if corridor and non_corridor_exists:
                continue
            result.append(mv)
        return result

    def _ordered_moves(self, board: Board, moves: list[Move]) -> list[Move]:
        """Order moves for better alpha-beta pruning: carpets > primes > plains."""
        src = board.player_worker.get_location()

        def order_key(mv: Move) -> tuple[float, float, tuple]:
            if mv.move_type == MoveType.CARPET:
                guaranteed = float(CARPET_POINTS_TABLE[min(mv.roll_length, 7)])
                denial = self._local_denial_bonus(board, mv)
                return (0.0, -(guaranteed + denial), self.policy.move_sort_key(mv))

            dest = loc_after_direction(src, mv.direction) if mv.direction else src
            exits = 0.0
            ahead = 0.0
            alignment = 0.0
            if board.is_valid_cell(dest):
                board_after = board.forecast_move(mv, check_ok=False)
                if board_after is not None:
                    exits = float(self.policy._count_plain_exits(board_after, dest))
                ahead = float(self.policy._contiguous_primeable_ahead(board, dest, mv.direction))
                alignment = float(self.policy._chain_alignment_behind(board, src, mv.direction))

            if mv.move_type == MoveType.PRIME:
                score = 1.40 * self._potential_at(board, dest) + self.chain_potential_weight * (ahead + alignment) + 0.40 * exits
                return (1.0, -score, self.policy.move_sort_key(mv))

            score = 1.20 * self._potential_at(board, dest) + 0.20 * alignment + 0.10 * ahead + 0.50 * exits
            return (2.0, -score, self.policy.move_sort_key(mv))

        return sorted(moves, key=order_key)

    # ------------------------------------------------------------------ #
    #  Static Evaluation — Multi-Signal                                   #
    # ------------------------------------------------------------------ #

    def _advanced_static_eval(self, board: Board) -> float:
        """Evaluate board from our perspective using structural + rat + temporal signals."""
        analysis = self._get_analysis(board)
        our_idx = analysis.player_idx
        opp_idx = analysis.opponent_idx

        # --- Structural signals ---
        our_potential = self._potential_at_idx(board, our_idx, analysis)
        opp_potential = self._potential_at_idx(board, opp_idx, analysis)
        potential_diff = our_potential - opp_potential

        our_chain = analysis.best_chain_profile(our_idx, include_occupied=True)["composite_value"]
        opp_chain = analysis.best_chain_profile(opp_idx, include_occupied=True)["composite_value"]

        our_exits = self._exit_count_at(board, our_idx)
        opp_exits = self._exit_count_at(board, opp_idx)
        exit_count_diff = float(our_exits - opp_exits)

        our_entry = analysis.dist_to_nearest_entry(our_idx)
        opp_entry = analysis.dist_to_nearest_entry(opp_idx)
        our_entry_eff = 6.0 if our_entry is None else float(min(6, our_entry))
        opp_entry_eff = 6.0 if opp_entry is None else float(min(6, opp_entry))
        nearest_entry_advantage = opp_entry_eff - our_entry_eff

        trap_risk_diff = self._trap_risk(analysis, our_idx) - self._trap_risk(analysis, opp_idx)

        # --- Temporal discounting on chain values ---
        turns_left = board.player_worker.turns_left
        our_chain_discounted = our_chain * self._temporal_discount(turns_left, int(our_entry_eff))
        opp_chain_discounted = opp_chain * self._temporal_discount(
            board.opponent_worker.turns_left, int(opp_entry_eff)
        )
        discounted_chain_diff = our_chain_discounted - opp_chain_discounted

        # --- Rat opportunity signal (depth-diffused belief, BFS distance) ---
        rat_signal = 0.0
        if self._diffused_beliefs and self.root_board is not None:
            depth_from_root = max(0, min(5, abs(board.turn_count - self.root_board.turn_count)))
            belief = self._belief_at_depth(depth_from_root)
            if belief is not None:
                rat_signal = self._rat_opportunity_signal(board, belief, analysis)

        # --- Combine with pre-computed score context weights ---
        aggression = self._aggression
        safety = self._safety

        structural = (
            self.eval_potential_w * potential_diff
            + self.eval_chain_w * aggression * self.chain_potential_weight * discounted_chain_diff
            + self.eval_exit_w * safety * exit_count_diff
            + self.eval_entry_adv_w * nearest_entry_advantage
            - self.eval_trap_w * safety * trap_risk_diff
        )

        return structural + self.eval_rat_w * rat_signal

    # ------------------------------------------------------------------ #
    #  New Signal Components                                              #
    # ------------------------------------------------------------------ #

    def _rat_opportunity_signal(self, board: Board, belief: np.ndarray,
                                analysis: BoardAnalysis) -> float:
        """Positional search option value using walkable BFS distance."""
        player_idx = analysis.player_idx

        nearby_prob = 0.0
        peak_nearby = 0.0
        for idx in range(BOARD_CELLS):
            bfs_dist = analysis.dist(player_idx, idx)
            if bfs_dist <= 3:
                nearby_prob += belief[idx]
                peak_nearby = max(peak_nearby, float(belief[idx]))

        return self.rat_nearby_w * nearby_prob + self.rat_peak_w * max(0.0, peak_nearby - self.rat_peak_thresh)

    @staticmethod
    def _score_context_modifier(root_board: Board) -> tuple[float, float]:
        """Returns (aggression_scale, safety_scale) from the root board's score state.

        Called ONCE before tree search. Stored and reused for all leaf evals.
        """
        my_score = root_board.player_worker.get_points()
        opp_score = root_board.opponent_worker.get_points()
        diff = my_score - opp_score
        turns_left = root_board.player_worker.turns_left

        urgency_weight = max(0.5, min(2.0, 40.0 / max(1, turns_left)))
        effective_diff = diff * urgency_weight

        if effective_diff >= 10:
            return (0.7, 1.4)
        elif effective_diff >= 4:
            return (0.85, 1.15)
        elif effective_diff >= -4:
            return (1.0, 1.0)
        elif effective_diff >= -10:
            return (1.25, 0.75)
        else:
            return (1.4, 0.6)

    @staticmethod
    def _temporal_discount(turns_left: int, distance_to_entry: int) -> float:
        """Discount factor for chain values that require movement to access."""
        if distance_to_entry <= 0:
            return 1.0
        if turns_left <= distance_to_entry + 1:
            return 0.1
        slack = (turns_left - distance_to_entry) / max(1, turns_left)
        return max(0.1, min(1.0, slack))

    def _belief_at_depth(self, depth_from_root: int) -> np.ndarray | None:
        """Return the depth-diffused belief, or None if unavailable."""
        if not self._diffused_beliefs:
            return None
        d = min(depth_from_root, max(self._diffused_beliefs.keys()))
        return self._diffused_beliefs.get(d)

    # ------------------------------------------------------------------ #
    #  Helper Methods                                                     #
    # ------------------------------------------------------------------ #

    def _potential_at(self, board: Board, loc: tuple[int, int]) -> float:
        """Lightweight cell potential: chain value + exit bonus + carpet scoring."""
        if not board.is_valid_cell(loc):
            return 0.0
        value = 0.0
        for d in _DIRECTIONS:
            k = self.policy._adjacent_primed_chain_len(board, loc, d)
            if k >= 2:
                value = max(value, 0.5 * float(CARPET_POINTS_TABLE[min(k, 7)]))
        # Spatial bonus: nearby space cells
        space_adj = 0
        for d in _DIRECTIONS:
            nxt = loc_after_direction(loc, d)
            if board.is_valid_cell(nxt) and board.get_cell(nxt).name == "SPACE":
                space_adj += 1
        value += 0.15 * space_adj
        return value

    def _potential_at_idx(self, board: Board, idx: int, analysis: BoardAnalysis) -> float:
        """Cell potential at a board index."""
        loc = _index_to_loc(idx)
        return self._potential_at(board, loc)

    def _exit_count_at(self, board: Board, idx: int) -> int:
        """Count plain exits available from a cell index."""
        loc = _index_to_loc(idx)
        count = 0
        for nxt in _NEIGHBORS_BY_INDEX[idx]:
            nxt_loc = _index_to_loc(nxt)
            if not board.is_cell_blocked(nxt_loc):
                count += 1
        return count

    def _trap_risk(self, analysis: BoardAnalysis, cell: int) -> float:
        """Evaluate trap risk at a cell index."""
        loc = _index_to_loc(cell)
        exits = self._exit_count_at(analysis.board, cell)
        risk = max(0.0, 1.5 - 0.5 * float(exits))
        # Check corridor trap: single exit whose only exit also has <=1 exits
        if exits == 1:
            for nxt in _NEIGHBORS_BY_INDEX[cell]:
                nxt_loc = _index_to_loc(nxt)
                if not analysis.board.is_cell_blocked(nxt_loc):
                    nxt_exits = self._exit_count_at(analysis.board, nxt)
                    if nxt_exits <= 1:
                        risk += 1.0
                    break
        return risk

    def _transition(self, board: Board, mv: Move) -> tuple[float, Board] | None:
        """Forecast a move and return (immediate_points, resulting_board)."""
        if mv.move_type == MoveType.SEARCH:
            return None
        if mv.move_type == MoveType.CARPET and mv.roll_length <= 1:
            return None

        board_after = board.forecast_move(mv, check_ok=False)
        if board_after is None:
            return None

        dest = self.policy._destination(board, mv)
        exits = self.policy._count_plain_exits(board_after, dest)
        if exits == 0:
            return None
        if mv.move_type == MoveType.PRIME and exits < 2:
            return None

        return self._immediate_points(mv), board_after

    def _local_denial_bonus(self, board: Board, mv: Move) -> float:
        """Bonus for carpet moves that deny opponent access to valuable cells."""
        if mv.move_type != MoveType.CARPET:
            return 0.0
        opp_loc = board.opponent_worker.get_location()
        src = board.player_worker.get_location()
        cur = src
        denied = 0
        for _ in range(mv.roll_length):
            cur = loc_after_direction(cur, mv.direction)
            if abs(cur[0] - opp_loc[0]) + abs(cur[1] - opp_loc[1]) <= 2:
                denied += 1
        return 0.5 * denied

    @staticmethod
    def _immediate_points(mv: Move) -> float:
        if mv.move_type == MoveType.PRIME:
            return 1.0
        if mv.move_type == MoveType.CARPET:
            return float(CARPET_POINTS_TABLE[min(mv.roll_length, 7)])
        return 0.0

    def _get_analysis(self, board: Board) -> BoardAnalysis:
        """Get or create a cached BoardAnalysis for a board state."""
        key = self._board_key(board)
        cached = self._analysis_cache.get(key)
        if cached is not None:
            return cached
        analysis = BoardAnalysis(board)
        self._analysis_cache[key] = analysis
        return analysis

    @staticmethod
    def _board_key(board: Board) -> tuple:
        return (
            board._space_mask,
            board._primed_mask,
            board._carpet_mask,
            board.player_worker.get_location(),
            board.opponent_worker.get_location(),
        )

    def _check_deadline(self) -> None:
        self._nodes += 1
        if (self._nodes & 127) == 0 and time.perf_counter() >= self._deadline:
            raise _SearchTimeout
