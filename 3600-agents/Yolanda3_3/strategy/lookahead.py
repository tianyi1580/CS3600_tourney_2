from __future__ import annotations

import time
from typing import TYPE_CHECKING

from game.board import Board
from game.enums import CARPET_POINTS_TABLE, Direction, MoveType, loc_after_direction
from game.move import Move

if TYPE_CHECKING:
    from .board_analysis import BoardAnalysis
    from .policy import PolicyEngine


_DIRECTIONS: tuple[Direction, Direction, Direction, Direction] = (
    Direction.UP,
    Direction.DOWN,
    Direction.LEFT,
    Direction.RIGHT,
)


class _SearchTimeout(Exception):
    pass


class Lookahead:
    """Competitive multi-agent minimax search with point-differential logic."""

    DEPTHS: tuple[int, ...] = (2, 3, 4, 5) # Shallow minimax; 5 for better anticipation

    def __init__(self, policy: PolicyEngine, root_analysis: BoardAnalysis | None = None) -> None:
        self.policy = policy
        self.root_analysis = root_analysis
        self._deadline = 0.0
        self._nodes = 0

    def rank_moves(
        self,
        board: Board,
        candidates: list[Move],
        time_budget_s: float,
    ) -> tuple[Move | None, float, bool]:
        if not candidates or time_budget_s <= 0.0:
            return None, float("-inf"), False

        start = time.perf_counter()
        self._deadline = start + time_budget_s
        self._nodes = 0

        ordered_root = self._ordered_moves(board, candidates, is_enemy=False)

        best_move: Move | None = None
        best_value = float("-inf")
        completed_depth2 = False

        for depth in self.DEPTHS:
            if time.perf_counter() - start >= time_budget_s * 0.9:
                break
            try:
                # We start at depth D, which is our turn (maximizing).
                move_d, value_d = self._search_at_depth_minimax(board, ordered_root, depth)
            except _SearchTimeout:
                break
            if move_d is None:
                continue
            best_move = move_d
            best_value = value_d
            if depth >= 2:
                completed_depth2 = True

        return best_move, best_value, completed_depth2

    def _search_at_depth_minimax(self, board: Board, root_moves: list[Move], depth: int) -> tuple[Move | None, float]:
        best_move: Move | None = None
        best = float("-inf")
        alpha = float("-inf")
        beta = float("inf")
        
        for mv in root_moves:
            self._check_deadline()
            nxt = self._transition(board, mv, is_enemy=False)
            if nxt is None:
                continue
            gain, board_next = nxt
            # After our move, it's the opponent's turn (minimizing our point differential).
            val = gain + self._minimax_search(board_next, depth - 1, False, alpha - gain, beta - gain)
            if val > best or (val == best and best_move is not None and self.policy.move_sort_key(mv) < self.policy.move_sort_key(best_move)):
                best = val
                best_move = mv
            if best > alpha:
                alpha = best
            if alpha >= beta:
                break

        return best_move, best

    def _minimax_search(self, board: Board, depth: int, maximizing: bool, alpha: float, beta: float) -> float:
        self._check_deadline()

        if depth <= 0:
            return self.static_eval_differential(board)

        # Handle perspective for move generation and ordering without cloning the whole board
        if not maximizing:
            board.reverse_perspective()
        
        valid_moves = board.get_valid_moves(exclude_search=True)
        moves = self._ordered_moves(board, valid_moves, is_enemy=not maximizing)
        
        if not maximizing:
            board.reverse_perspective() # restore original perspective

        if not moves:
            return self.static_eval_differential(board)

        if maximizing:
            best = float("-inf")
            for mv in moves:
                nxt = self._transition(board, mv, is_enemy=False)
                if nxt is None:
                    continue
                gain, board_next = nxt
                val = gain + self._minimax_search(board_next, depth - 1, False, alpha - gain, beta - gain)
                best = max(best, val)
                alpha = max(alpha, best)
                if alpha >= beta:
                    break
            return best if best != float("-inf") else self.static_eval_differential(board)
        else:
            best = float("inf")
            for mv in moves:
                # Simulate opponent move: reverse, forecast, and reverse back for consistency
                board.reverse_perspective()
                nxt = self._transition(board, mv, is_enemy=False)
                board.reverse_perspective() # restore
                
                if nxt is None:
                    continue
                gain, board_next = nxt
                # board_next now has opponent as player_worker and our worker as opponent_worker.
                # To maintain a stable perspective in recursive calls, we reverse board_next back to OUR perspective.
                board_next.reverse_perspective()
                
                val = -gain + self._minimax_search(board_next, depth - 1, True, alpha + gain, beta + gain)
                best = min(best, val)
                beta = min(beta, best)
                if alpha >= beta:
                    break
            return best if best != float("inf") else self.static_eval_differential(board)

    def _transition(self, board: Board, mv: Move, is_enemy: bool) -> tuple[float, Board] | None:
        if mv.move_type == MoveType.SEARCH:
            return None
        if mv.move_type == MoveType.CARPET and mv.roll_length <= 1:
            return None

        # Basic validity check (excluding expensive reachability for recursion speed)
        board_after = board.forecast_move(mv, check_ok=False)
        if board_after is None:
            return None

        dest = self.policy._destination(board, mv)
        exits = self.policy._count_plain_exits(board_after, dest)
        if exits == 0:
            return None
            
        # Tactical veto restoration: avoid primes that leave us no escape (§13.4 logic)
        if mv.move_type == MoveType.PRIME and exits < 2:
            return None

        return self._immediate_points(mv), board_after

    def static_eval_differential(self, board: Board) -> float:
        """Evaluates point differential potential from the current perspective without board copies."""
        # Our perspective
        worker_pos = board.player_worker.get_location()
        our_score = 0.0
        for direction in _DIRECTIONS:
            k = self.policy._adjacent_primed_chain_len(board, worker_pos, direction)
            if k >= 2:
                our_score = max(our_score, 0.7 * float(CARPET_POINTS_TABLE[min(k, 7)]))
        our_score += 0.2 * float(self.policy._count_plain_exits(board, worker_pos))

        # Opponent perspective (calculated directly from the same board)
        opp_pos = board.opponent_worker.get_location()
        opp_score = 0.0
        for direction in _DIRECTIONS:
            k = self.policy._adjacent_primed_chain_len(board, opp_pos, direction)
            if k >= 2:
                opp_score = max(opp_score, 0.7 * float(CARPET_POINTS_TABLE[min(k, 7)]))
        opp_score += 0.2 * float(self.policy._count_plain_exits(board, opp_pos))

        return our_score - opp_score

    def _ordered_moves(self, board: Board, moves: list[Move], is_enemy: bool) -> list[Move]:
        # 'board' has player_worker as the one currently moving.
        src = board.player_worker.get_location()

        def order_key(mv: Move) -> tuple:
            # Carpet moves first (highest points)
            if mv.move_type == MoveType.CARPET:
                return (0, -float(CARPET_POINTS_TABLE[min(mv.roll_length, 7)]), self.policy.move_sort_key(mv))
            # Prime moves that extend chains
            if mv.move_type == MoveType.PRIME:
                dest = loc_after_direction(src, mv.direction)
                ahead = 0
                behind = 0
                if board.is_valid_cell(dest):
                    ahead = self.policy._contiguous_primeable_ahead(board, dest, mv.direction)
                    behind = self.policy._chain_alignment_behind(board, src, mv.direction)
                return (1, -(ahead + behind), self.policy.move_sort_key(mv))
            # Plain moves toward the center or exits
            if mv.move_type == MoveType.PLAIN:
                dest = loc_after_direction(src, mv.direction)
                exits = 0
                if board.is_valid_cell(dest):
                    exits = self.policy._count_plain_exits(board, dest)
                return (2, -exits, self.policy.move_sort_key(mv))
            return (3, 0, self.policy.move_sort_key(mv))

        return sorted(moves, key=order_key)

    @staticmethod
    def _immediate_points(mv: Move) -> float:
        if mv.move_type == MoveType.PRIME:
            return 1.0
        if mv.move_type == MoveType.CARPET:
            return float(CARPET_POINTS_TABLE[min(mv.roll_length, 7)])
        return 0.0

    def _check_deadline(self) -> None:
        self._nodes += 1
        # Increased frequency of deadline checks since nodes are now faster
        if (self._nodes & 127) == 0 and time.perf_counter() >= self._deadline:
            raise _SearchTimeout
