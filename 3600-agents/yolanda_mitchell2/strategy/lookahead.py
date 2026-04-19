from __future__ import annotations

import time
from typing import TYPE_CHECKING

from game.board import Board
from game.enums import CARPET_POINTS_TABLE, Direction, MoveType, loc_after_direction
from game.move import Move

if TYPE_CHECKING:
    from .board_analysis import BoardAnalysis
    from .policy import PolicyEngine
    from ..tracking.belief import BeliefEngine


from .constants import OPENING_PERPENDICULAR_PENALTY, CARPET_PRIORITY_BONUS

_DIRECTIONS: tuple[Direction, Direction, Direction, Direction] = (
    Direction.UP,
    Direction.DOWN,
    Direction.LEFT,
    Direction.RIGHT,
)


class _SearchTimeout(Exception):
    pass


class Lookahead:
    """Single-agent iterative-deepening search with alpha-window pruning."""

    DEPTHS: tuple[int, ...] = (2, 3, 4, 5, 6)

    def __init__(self, policy: PolicyEngine, root_analysis: BoardAnalysis | None = None) -> None:
        self.policy = policy
        self.root_analysis = root_analysis
        self._deadline = 0.0
        self._nodes = 0

    def rank_moves(
        self,
        board: Board,
        belief: BeliefEngine,
        candidates: list[Move],
        time_budget_s: float,
    ) -> tuple[Move | None, float, bool]:
        if not candidates or time_budget_s <= 0.0:
            return None, float("-inf"), False

        start = time.perf_counter()
        self._deadline = start + time_budget_s
        self._nodes = 0

        ordered_root = self._ordered_moves(board, candidates)

        best_move: Move | None = None
        best_value = float("-inf")
        completed_depth2 = False

        for depth in self.DEPTHS:
            if time.perf_counter() - start >= time_budget_s * 0.9:
                break
            try:
                move_d, value_d = self._search_at_depth(board, belief, ordered_root, depth)
            except _SearchTimeout:
                break
            if move_d is None:
                continue
            best_move = move_d
            best_value = value_d
            if depth >= 2:
                completed_depth2 = True

        return best_move, best_value, completed_depth2

    def _search_at_depth(self, board: Board, belief: BeliefEngine, root_moves: list[Move], depth: int) -> tuple[Move | None, float]:
        best_move: Move | None = None
        best = float("-inf")
        alpha = float("-inf")
        beta = float("inf")
        point_exists = self._point_action_exists(root_moves)
        
        turns_left = board.player_worker.turns_left
        phase = self.policy._get_phase(turns_left)

        for mv in root_moves:
            self._check_deadline()
            nxt = self._transition(board, mv, point_exists)
            if nxt is None:
                continue
            gain, board_next = nxt
            val = gain + self._ab_search(board_next, belief, depth - 1, alpha - gain, beta - gain)
            
            # Apply heuristic modifiers to the search value for root move ranking
            if mv.move_type == MoveType.CARPET and mv.roll_length >= 3:
                val += CARPET_PRIORITY_BONUS
                
            if phase == "opening":
                opp_loc = board.opponent_worker.get_location()
                src = board.player_worker.get_location()
                if src[1] == opp_loc[1] and mv.direction in (Direction.UP, Direction.DOWN):
                    pass
                elif src[0] == opp_loc[0] and mv.direction in (Direction.LEFT, Direction.RIGHT):
                    pass
                elif src[1] != opp_loc[1] and mv.direction in (Direction.LEFT, Direction.RIGHT):
                    val -= OPENING_PERPENDICULAR_PENALTY
                elif src[0] != opp_loc[0] and mv.direction in (Direction.UP, Direction.DOWN):
                    val -= OPENING_PERPENDICULAR_PENALTY

            if val > best or (val == best and best_move is not None and self.policy.move_sort_key(mv) < self.policy.move_sort_key(best_move)):
                best = val
                best_move = mv
            if best > alpha:
                alpha = best

        return best_move, best

    def _ab_search(self, board: Board, belief: BeliefEngine, depth: int, alpha: float, beta: float) -> float:
        self._check_deadline()

        if depth <= 0:
            return self.static_eval(board, belief)

        moves = self._ordered_moves(board, board.get_valid_moves(exclude_search=True))
        if not moves:
            return self.static_eval(board, belief)

        point_exists = self._point_action_exists(moves)
        best = float("-inf")

        for mv in moves:
            nxt = self._transition(board, mv, point_exists)
            if nxt is None:
                continue
            gain, board_next = nxt
            val = gain + self._ab_search(board_next, belief, depth - 1, alpha - gain, beta - gain)
            if val > best:
                best = val
            if best > alpha:
                alpha = best
            if alpha >= beta:
                break

        return best if best != float("-inf") else self.static_eval(board, belief)

    def _transition(self, board: Board, mv: Move, point_exists: bool) -> tuple[float, Board] | None:
        if mv.move_type == MoveType.SEARCH:
            return None
        if mv.move_type == MoveType.CARPET and mv.roll_length <= 1:
            return None

        if point_exists and board.player_worker.turns_left <= 1 and mv.move_type == MoveType.PLAIN:
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

    def static_eval(self, board: Board, belief: BeliefEngine) -> float:
        worker_pos = board.player_worker.get_location()
        score = 0.0

        # Reward primed chains
        for direction in _DIRECTIONS:
            k = self.policy._adjacent_primed_chain_len(board, worker_pos, direction)
            if k >= 3:
                score = max(score, 1.5 * float(CARPET_POINTS_TABLE[min(k, 7)]))
            elif k >= 2:
                score = max(score, 0.8 * float(CARPET_POINTS_TABLE[min(k, 7)]))

        # Mobility and center control
        exits = self.policy._count_plain_exits(board, worker_pos)
        score += 0.8 * float(exits)
        if exits <= 1:
            score -= 5.0

        dist_to_center = abs(worker_pos[0] - 3.5) + abs(worker_pos[1] - 3.5)
        score += (7.0 - dist_to_center) * 0.4

        # Rat proximity and entrapment bonus
        top_locs = belief.topk(5)
        for loc, p in top_locs:
            dist = abs(worker_pos[0] - loc[0]) + abs(worker_pos[1] - loc[1])
            score += p * max(0, 10 - dist) * 1.0
            
            # Entrapment: Reward being between the rat and the center or exits
            # This is a simple heuristic: if our distance to center is less than rat's,
            # we are likely between it and the center.
            rat_dist_to_center = abs(loc[0] - 3.5) + abs(loc[1] - 3.5)
            if dist_to_center < rat_dist_to_center:
                score += p * 2.0

        opp_pos = board.opponent_worker.get_location()
        manhattan = abs(worker_pos[0] - opp_pos[0]) + abs(worker_pos[1] - opp_pos[1])
        if manhattan <= 1:
            score -= 2.0

        return score

    def _ordered_moves(self, board: Board, moves: list[Move]) -> list[Move]:
        src = board.player_worker.get_location()

        def order_key(mv: Move) -> tuple:
            if mv.move_type == MoveType.CARPET:
                return (0, -float(CARPET_POINTS_TABLE[min(mv.roll_length, 7)]), self.policy.move_sort_key(mv))
            if mv.move_type == MoveType.PRIME:
                dest = loc_after_direction(src, mv.direction)
                ahead = 0
                behind = 0
                if board.is_valid_cell(dest):
                    ahead = self.policy._contiguous_primeable_ahead(board, dest, mv.direction)
                    behind = self.policy._chain_alignment_behind(board, src, mv.direction)
                return (1, -(ahead + behind), self.policy.move_sort_key(mv))
            if mv.move_type == MoveType.PLAIN:
                dest = loc_after_direction(src, mv.direction)
                exits = 0
                if board.is_valid_cell(dest):
                    exits = self.policy._count_plain_exits(board, dest)
                return (2, -exits, self.policy.move_sort_key(mv))
            return (3, 0, self.policy.move_sort_key(mv))

        return sorted(moves, key=order_key)

    @staticmethod
    def _point_action_exists(moves: list[Move]) -> bool:
        for mv in moves:
            if mv.move_type == MoveType.PRIME:
                return True
            if mv.move_type == MoveType.CARPET and mv.roll_length > 1:
                return True
        return False

    @staticmethod
    def _immediate_points(mv: Move) -> float:
        if mv.move_type == MoveType.PRIME:
            return 1.0
        if mv.move_type == MoveType.CARPET:
            return float(CARPET_POINTS_TABLE[min(mv.roll_length, 7)])
        return 0.0

    def _check_deadline(self) -> None:
        self._nodes += 1
        if (self._nodes & 63) == 0 and time.perf_counter() >= self._deadline:
            raise _SearchTimeout
