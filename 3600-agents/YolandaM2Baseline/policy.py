from __future__ import annotations

import math
import time

from game.board import Board
from game.enums import CARPET_POINTS_TABLE, BOARD_SIZE, Direction, MoveType, loc_after_direction
from game.move import Move

from .belief import BeliefEngine
from .runtime_state import RuntimeState
from .time_manager import TimeManager


class PolicyEngine:
    """Candidate generation and deterministic action selection policy."""

    def __init__(
        self,
        search_topk: int = 6,
        search_radius: int = 1,
        a: float = 1.00,
        b: float = 0.45,
        c: float = 0.60,
        d: float = 0.35,
        e: float = 1.00,
        f: float = 0.75,
    ) -> None:
        self.search_topk = search_topk
        self.search_radius = search_radius
        self.a = a
        self.b = b
        self.c = c
        self.d = d
        self.e = e
        self.f = f

    @staticmethod
    def parse_search_tuple(raw: tuple[object, object] | None) -> tuple[tuple[int, int] | None, bool | None]:
        if not isinstance(raw, tuple) or len(raw) != 2:
            return None, None
        loc, result = raw
        if not (isinstance(loc, tuple) and len(loc) == 2):
            loc = None
        if result not in (True, False, None):
            result = None
        return loc, result

    def apply_search_channels(self, board: Board, belief: BeliefEngine, state: RuntimeState) -> None:
        if board.opponent_search != state.last_opponent_search:
            loc, result = self.parse_search_tuple(board.opponent_search)
            belief.apply_search_feedback(loc, result)
            state.last_opponent_search = board.opponent_search

        if board.player_search != state.last_player_search:
            loc, result = self.parse_search_tuple(board.player_search)
            belief.apply_search_feedback(loc, result)
            state.last_player_search = board.player_search

    def _candidate_search_locations(self, board: Board, belief: BeliefEngine) -> list[tuple[int, int]]:
        locs: list[tuple[int, int]] = []
        seen: set[tuple[int, int]] = set()

        for loc, _ in belief.topk(self.search_topk):
            if loc not in seen:
                seen.add(loc)
                locs.append(loc)

            for dx in range(-self.search_radius, self.search_radius + 1):
                for dy in range(-self.search_radius, self.search_radius + 1):
                    nloc = (loc[0] + dx, loc[1] + dy)
                    if not board.is_valid_cell(nloc):
                        continue
                    if nloc not in seen:
                        seen.add(nloc)
                        locs.append(nloc)

        return locs

    @staticmethod
    def move_sort_key(move: Move) -> tuple:
        if move.move_type == MoveType.SEARCH:
            return (3, move.search_loc[1], move.search_loc[0])
        if move.move_type == MoveType.CARPET:
            return (2, int(move.direction), move.roll_length)
        if move.move_type == MoveType.PRIME:
            return (1, int(move.direction), 0)
        return (0, int(move.direction), 0)

    def generate_candidates(self, board: Board, belief: BeliefEngine) -> list[Move]:
        candidates: list[Move] = []
        seen: set[tuple] = set()

        for move in board.get_valid_moves(exclude_search=True):
            if board.is_valid_move(move):
                key = (move.move_type, move.direction, move.roll_length, move.search_loc)
                if key not in seen:
                    seen.add(key)
                    candidates.append(move)

        for loc in self._candidate_search_locations(board, belief):
            smove = Move.search(loc)
            if board.is_valid_move(smove):
                key = (smove.move_type, smove.direction, smove.roll_length, smove.search_loc)
                if key not in seen:
                    seen.add(key)
                    candidates.append(smove)

        candidates.sort(key=self.move_sort_key)
        return candidates

    def _destination(self, board: Board, action: Move) -> tuple[int, int]:
        src = board.player_worker.get_location()
        if action.move_type in (MoveType.PLAIN, MoveType.PRIME):
            return loc_after_direction(src, action.direction)
        if action.move_type == MoveType.CARPET:
            cur = src
            for _ in range(action.roll_length):
                cur = loc_after_direction(cur, action.direction)
            return cur
        return src

    def _chain_score(self, board_after: Board, dest: tuple[int, int]) -> float:
        best = 0.0
        for direction in (Direction.UP, Direction.DOWN, Direction.LEFT, Direction.RIGHT):
            cur = dest
            k = 0
            while k < BOARD_SIZE - 1:
                cur = loc_after_direction(cur, direction)
                if not board_after.is_valid_cell(cur):
                    break
                if board_after.get_cell(cur).name != "PRIMED":
                    break
                k += 1
            if k >= 2:
                best = max(best, float(CARPET_POINTS_TABLE[min(k, 7)]))
        return best

    def _risk_score(self, post_move_legal_moves: int) -> float:
        risk = max(0.0, 1.0 - post_move_legal_moves / 4.0)
        if post_move_legal_moves <= 1:
            risk += 0.3
        return risk

    def score_non_search(self, board: Board, action: Move, belief: BeliefEngine) -> tuple[float, dict[str, float]]:
        if action.move_type == MoveType.SEARCH:
            return float("-inf"), {"mobility": 0.0, "immediate": 0.0, "risk": 0.0}

        board_after = board.forecast_move(action, check_ok=True)
        if board_after is None:
            return float("-inf"), {"mobility": 0.0, "immediate": 0.0, "risk": 1.0}

        immediate = 0.0
        if action.move_type == MoveType.PRIME:
            immediate = 1.0
        elif action.move_type == MoveType.CARPET:
            immediate = float(CARPET_POINTS_TABLE[action.roll_length])

        dest = self._destination(board, action)
        post_moves = board_after.get_valid_moves(exclude_search=True)
        post_move_count = len(post_moves)
        center_dist = abs(dest[0] - 3.5) + abs(dest[1] - 3.5)
        centrality = 1.0 - center_dist / 7.0
        position = (post_move_count / 4.0) + 0.3 * centrality

        carpet_setup = self._chain_score(board_after, dest)

        opponent_moves = len(board_after.get_valid_moves(enemy=True, exclude_search=True))
        denial = max(0.0, 8.0 - opponent_moves) / 8.0

        risk = self._risk_score(post_move_count)

        total = (
            self.a * immediate
            + self.b * position
            + self.c * carpet_setup
            + self.d * denial
            + self.e * 0.0
            - self.f * risk
        )

        return total, {"mobility": float(post_move_count), "immediate": immediate, "risk": risk}

    @staticmethod
    def score_search(belief: BeliefEngine, search_move: Move) -> float:
        if search_move.move_type != MoveType.SEARCH or search_move.search_loc is None:
            return float("-inf")
        p = belief.probability_at(search_move.search_loc)
        return 6.0 * p - 2.0

    @staticmethod
    def _update_welford(value: float, count: int, mean: float, m2: float) -> tuple[int, float, float, float]:
        count += 1
        delta = value - mean
        mean += delta / count
        delta2 = value - mean
        m2 += delta * delta2
        variance = m2 / (count - 1) if count > 1 else 1.0
        sigma = math.sqrt(max(variance, 1e-12))
        return count, mean, m2, sigma

    @staticmethod
    def _normalize(value: float, mean: float, sigma: float, eps: float) -> float:
        return (value - mean) / max(sigma, eps)

    def _margin(self, board: Board, time_remaining: float) -> float:
        my_score = board.player_worker.get_points()
        opp_score = board.opponent_worker.get_points()
        margin = 0.0
        if my_score < opp_score:
            margin = -0.10
        elif my_score > opp_score:
            margin = 0.10
        if time_remaining < 8.0:
            margin += 0.15
        return margin

    def _best_safe_non_search(self, board: Board) -> Move:
        moves = board.get_valid_moves(exclude_search=True)
        plain_moves = [m for m in moves if m.move_type == MoveType.PLAIN]
        if plain_moves:
            plain_moves.sort(key=self.move_sort_key)
            return plain_moves[0]
        moves.sort(key=self.move_sort_key)
        return moves[0]

    def select_action(
        self,
        board: Board,
        belief: BeliefEngine,
        state: RuntimeState,
        time_left,
    ) -> Move:
        now = float(time_left())
        alloc, emergency = TimeManager.allocation(board, state, now)
        turn_deadline = time.perf_counter() + alloc

        candidates = self.generate_candidates(board, belief)
        if not candidates:
            return self._best_safe_non_search(board)

        if emergency or now <= state.emergency_floor_total:
            fallback = self._best_safe_non_search(board)
            state.fallback_move = fallback
            state.fallback_turn = board.turn_count
            return fallback

        best_non_search: Move | None = None
        best_non_search_score = float("-inf")
        best_non_search_meta = {"mobility": 0.0, "immediate": 0.0, "risk": 0.0}

        best_search: Move | None = None
        best_search_score = float("-inf")

        for mv in candidates:
            if time.perf_counter() >= turn_deadline:
                break

            if mv.move_type == MoveType.SEARCH:
                sv = self.score_search(belief, mv)
                if sv > best_search_score or (
                    sv == best_search_score
                    and best_search is not None
                    and self.move_sort_key(mv) < self.move_sort_key(best_search)
                ):
                    best_search = mv
                    best_search_score = sv
                continue

            tv, meta = self.score_non_search(board, mv, belief)
            if tv > best_non_search_score or (
                tv == best_non_search_score
                and (
                    meta["mobility"],
                    meta["immediate"],
                    -meta["risk"],
                    tuple(self.move_sort_key(mv)),
                )
                > (
                    best_non_search_meta["mobility"],
                    best_non_search_meta["immediate"],
                    -best_non_search_meta["risk"],
                    tuple(self.move_sort_key(best_non_search)) if best_non_search else (999, 999, 999),
                )
            ):
                best_non_search = mv
                best_non_search_score = tv
                best_non_search_meta = meta

        # Keep online normalization stable for cross-family comparisons.
        state.ev_count, state.mu_ev, state.ev_m2, state.sigma_ev = self._update_welford(
            best_search_score if best_search is not None else -2.0,
            state.ev_count,
            state.mu_ev,
            state.ev_m2,
        )
        state.t_count, state.mu_t, state.t_m2, state.sigma_t = self._update_welford(
            best_non_search_score if best_non_search is not None else -1e6,
            state.t_count,
            state.mu_t,
            state.t_m2,
        )

        normalized_search = self._normalize(
            best_search_score if best_search is not None else -2.0,
            state.mu_ev,
            state.sigma_ev,
            state.eps,
        )
        normalized_tactical = self._normalize(
            best_non_search_score if best_non_search is not None else -1e6,
            state.mu_t,
            state.sigma_t,
            state.eps,
        )

        selected: Move
        if best_search is not None and normalized_search >= normalized_tactical + self._margin(board, now):
            selected = best_search
        elif best_non_search is not None:
            selected = best_non_search
        else:
            selected = self._best_safe_non_search(board)

        if not board.is_valid_move(selected):
            selected = self._best_safe_non_search(board)

        state.fallback_move = selected
        state.fallback_turn = board.turn_count

        state.observed_turns += 1
        if selected.move_type == MoveType.PRIME:
            state.prime_heavy_turns += 1
        elif selected.move_type == MoveType.CARPET:
            state.carpet_heavy_turns += 1
        elif selected.move_type == MoveType.SEARCH:
            state.search_heavy_turns += 1

        return selected
