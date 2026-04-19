from __future__ import annotations

import math
from collections import deque

import numpy as np

from game.board import Board
from game.enums import CARPET_POINTS_TABLE, MoveType
from game.move import Move

from ..infra.runtime_state import RuntimeState
from ..infra.time_manager import TimeManager
from ..tracking.belief import BeliefEngine
from ..tracking.opponent_observation import infer_opponent_category
from .bitboard_search import BitboardSearch, SearchContext
from .bitboard_state import BitboardAdapter, loc_to_index, shortest_turn_distances
from .voronoi import VoronoiSnapshot


class PolicyEngine:
    """Yolanda6 policy shell using a shadow-state search core for non-search moves."""

    SEARCH_FLOOR_PROB = 0.40
    TT_MAX_ENTRIES = 100_000
    SEARCH_MAX_DEPTH = 6

    def __init__(
        self,
        *,
        ownership_safe_w: float = 1.05,
        ownership_contested_w: float = 1.35,
        ownership_dead_w: float = 0.85,
        lane_steal_w: float = 1.20,
        foraging_axis_w: float = 0.30,
        search_threat_w: float = 1.10,
        lead_margin_base: float = 0.20,
        lead_margin_slope: float = 0.03,
        lead_margin_cap: float = 1.20,
        lead_prob_floor_bonus: float = 0.08,
        bb_eval_mobility_w: float = 0.35,
        bb_eval_local_chain_w: float = 0.45,
        bb_eval_trap_w: float = 0.55,
        a: float = 1.40,
        b: float = 0.45,
        c: float = 1.20,
        d: float = 0.35,
        f: float = 0.75,
        **kwargs,
    ) -> None:
        del kwargs
        self.a = a
        self.b = b
        self.c = c
        self.d = d
        self.f = f
        self.ownership_safe_w = ownership_safe_w
        self.ownership_contested_w = ownership_contested_w
        self.ownership_dead_w = ownership_dead_w
        self.lane_steal_w = lane_steal_w
        self.foraging_axis_w = foraging_axis_w
        self.search_threat_w = search_threat_w
        self.lead_margin_base = lead_margin_base
        self.lead_margin_slope = lead_margin_slope
        self.lead_margin_cap = lead_margin_cap
        self.lead_prob_floor_bonus = lead_prob_floor_bonus
        self.bb_eval_mobility_w = bb_eval_mobility_w
        self.bb_eval_local_chain_w = bb_eval_local_chain_w
        self.bb_eval_trap_w = bb_eval_trap_w
        self.search_topk = 10
        self.search_radius = 2
        self._rollout_cache: dict[tuple, float] = {}
        self._active_root_board: Board | None = None
        self._active_root_analysis = None
        self._opp_carpet_threat_cells: set[tuple[int, int]] = set()
        self._opp_carpet_threat_value: float = 0.0

    @staticmethod
    def move_sort_key(move: Move) -> tuple:
        if move.move_type == MoveType.SEARCH:
            return (3, move.search_loc[1], move.search_loc[0])
        if move.move_type == MoveType.CARPET:
            return (2, int(move.direction), move.roll_length)
        if move.move_type == MoveType.PRIME:
            return (1, int(move.direction), 0)
        return (0, int(move.direction), 0)

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
        if board.player_search != state.last_player_search:
            loc, result = self.parse_search_tuple(board.player_search)
            belief.apply_search_feedback(loc, result, is_self=True)
            if result is True:
                state.use_single_step = False
            state.last_player_search = board.player_search

        if board.opponent_search != state.last_opponent_search:
            loc, result = self.parse_search_tuple(board.opponent_search)
            if result is True:
                belief.apply_search_feedback(loc, result, is_self=False)
                state.use_single_step = True
            elif result is False and loc is not None:
                state.opp_miss_cell = loc
            state.last_opponent_search = board.opponent_search

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
                    if board.is_valid_cell(nloc) and nloc not in seen:
                        seen.add(nloc)
                        locs.append(nloc)
        return locs

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

    @staticmethod
    def score_search(belief: BeliefEngine, search_move: Move) -> float:
        if search_move.move_type != MoveType.SEARCH or search_move.search_loc is None:
            return float("-inf")
        p = belief.probability_at(search_move.search_loc)
        return 6.0 * p - 2.0

    def _observe_opponent_and_maybe_adapt(self, board: Board, state: RuntimeState) -> None:
        cat = infer_opponent_category(state.snapshot_at_our_turn_start, state.last_own_move, board)
        opp_mob = len(board.get_valid_moves(enemy=True, exclude_search=True))
        state.opp_turn_buffer.append((cat, opp_mob))
        if cat is not None:
            state.observed_turns += 1
        if state.snapshot_at_our_turn_start is not None:
            ol, ors = self.parse_search_tuple(state.snapshot_at_our_turn_start.opponent_search)
            nl, nrs = self.parse_search_tuple(board.opponent_search)
            if nl is not None and nrs in (True, False) and (nl, nrs) != (ol, ors):
                state.opp_search_attempts += 1
                if nrs:
                    state.opp_search_correct += 1

    def _best_safe_non_search(self, board: Board) -> Move:
        moves = board.get_valid_moves(exclude_search=True)
        plain_moves = [m for m in moves if m.move_type == MoveType.PLAIN]
        if plain_moves:
            plain_moves.sort(key=self.move_sort_key)
            return plain_moves[0]
        if moves:
            moves.sort(key=self.move_sort_key)
            return moves[0]
        return board.get_valid_moves(exclude_search=False)[0]

    def _late_phase_filter_non_search(self, board: Board, moves: list[Move]) -> list[Move]:
        del board
        carpets_ge3 = [m for m in moves if m.move_type == MoveType.CARPET and m.roll_length >= 3]
        if carpets_ge3:
            return carpets_ge3
        carpets_2 = [m for m in moves if m.move_type == MoveType.CARPET and m.roll_length == 2]
        if carpets_2:
            return carpets_2
        primes = [m for m in moves if m.move_type == MoveType.PRIME]
        if primes:
            return primes
        plains = [m for m in moves if m.move_type == MoveType.PLAIN]
        if plains:
            return plains
        return moves

    @staticmethod
    def _belief_entropy(belief: BeliefEngine) -> float:
        probs = belief.belief
        mask = probs > 0.0
        if not np.any(mask):
            return 0.0
        entropy = float(-np.sum(probs[mask] * np.log(probs[mask])))
        return entropy / math.log(len(probs))

    @staticmethod
    def _recent_axis(state: RuntimeState) -> str | None:
        if len(state.recent_positions) < 3:
            return None
        p0, p1, p2 = list(state.recent_positions)[-3:]
        axis_1 = PolicyEngine._step_axis(p0, p1)
        axis_2 = PolicyEngine._step_axis(p1, p2)
        if axis_1 is not None and axis_1 == axis_2:
            return axis_1
        return None

    @staticmethod
    def _step_axis(a: tuple[int, int], b: tuple[int, int]) -> str | None:
        if a[1] == b[1] and a[0] != b[0]:
            return "horizontal"
        if a[0] == b[0] and a[1] != b[1]:
            return "vertical"
        return None

    def _build_search_context(
        self,
        board: Board,
        belief: BeliefEngine,
        state: RuntimeState,
    ) -> tuple[object, SearchContext]:
        root_state = BitboardAdapter.from_board(board)
        snapshot = VoronoiSnapshot.from_state(root_state)
        entropy = self._belief_entropy(belief)
        preferred_axis = self._recent_axis(state)
        allow_foraging = (
            entropy >= 0.78
            and preferred_axis is not None
            and snapshot.best_zone_value("safe") < 4.0
            and snapshot.best_zone_value("contested") < 4.0
        )
        context = SearchContext(
            snapshot=snapshot,
            ownership_safe_w=self.ownership_safe_w,
            ownership_contested_w=self.ownership_contested_w,
            ownership_dead_w=self.ownership_dead_w,
            lane_steal_w=self.lane_steal_w,
            foraging_axis_w=self.foraging_axis_w,
            belief_entropy=entropy,
            preferred_axis=preferred_axis,
            allow_foraging=allow_foraging,
            bb_eval_mobility_w=self.bb_eval_mobility_w,
            bb_eval_local_chain_w=self.bb_eval_local_chain_w,
            bb_eval_trap_w=self.bb_eval_trap_w,
        )
        return root_state, context

    def _best_search_candidate(
        self,
        search_candidates: list[Move],
        belief: BeliefEngine,
    ) -> tuple[Move | None, float, float]:
        best_move: Move | None = None
        best_ev = float("-inf")
        best_prob = 0.0
        for move in sorted(search_candidates, key=self.move_sort_key):
            ev = self.score_search(belief, move)
            prob = belief.probability_at(move.search_loc) if move.search_loc is not None else 0.0
            if ev > best_ev or (ev == best_ev and best_move is not None and self.move_sort_key(move) < self.move_sort_key(best_move)):
                best_move = move
                best_ev = ev
                best_prob = prob
        return best_move, best_ev, best_prob

    def _opponent_denial_value(
        self,
        root_state,
        belief: BeliefEngine,
        state: RuntimeState,
    ) -> float:
        top_cells = belief.topk(3)
        if not top_cells:
            return 0.0

        opp_dists = shortest_turn_distances(root_state, root_state.opponent_idx, root_state.player_idx)
        observed_turns = max(1, state.observed_turns)
        search_rate = state.opp_search_attempts / observed_turns if state.observed_turns > 0 else 0.18
        search_rate = max(0.10, min(0.75, search_rate))
        accuracy = state.opp_search_correct / max(1, state.opp_search_attempts) if state.opp_search_attempts else 0.35
        accuracy = max(0.20, min(0.80, accuracy))

        best_threat = 0.0
        for loc, prob in top_cells:
            dist = opp_dists[loc_to_index(loc)]
            if dist < 0 or dist > 3:
                continue
            tempo = (4.0 - float(dist)) / 4.0
            best_threat = max(best_threat, prob * tempo)

        # This is deliberately coarse. We need "can the opponent plausibly steal this rat soon?"
        # not a fake mirrored HMM built on observations they never received.
        return 4.0 * best_threat * search_rate * (0.5 + 0.5 * accuracy)

    @staticmethod
    def _board_gate_floor(move: Move) -> float:
        if move.move_type == MoveType.PRIME:
            return 1.0
        if move.move_type == MoveType.CARPET:
            return float(CARPET_POINTS_TABLE[min(move.roll_length, 7)])
        return 0.0

    def _lead_search_margin(self, score_diff: float) -> float:
        if score_diff <= 0.0:
            return 0.0
        margin = self.lead_margin_base + self.lead_margin_slope * score_diff
        return max(0.0, min(self.lead_margin_cap, margin))

    def select_action(
        self,
        board: Board,
        belief: BeliefEngine,
        state: RuntimeState,
        time_left,
    ) -> Move:
        now = float(time_left())
        alloc, emergency = TimeManager.allocation(board, state, now)
        search_window = max(0.0, alloc - TimeManager.expensive_work_cushion(state))
        self._rollout_cache.clear()

        if state.enable_opponent_model:
            self._observe_opponent_and_maybe_adapt(board, state)

        def _persist_return(move: Move) -> Move:
            state.effective_a = state.policy_base_a
            state.effective_b = self.b
            state.effective_c = state.policy_base_c
            state.effective_d = state.policy_base_d
            state.effective_f = state.policy_base_f
            self._active_root_board = None
            self._active_root_analysis = None
            self._opp_carpet_threat_cells = set()
            self._opp_carpet_threat_value = 0.0
            state.snapshot_at_our_turn_start = board.get_copy()
            state.last_own_move = move
            state.fallback_move = move
            state.fallback_turn = board.turn_count
            state.recent_positions.append(board.player_worker.get_location())
            return move

        candidates = self.generate_candidates(board, belief)
        if not candidates or emergency or now <= state.emergency_floor_total:
            return _persist_return(self._best_safe_non_search(board))

        search_candidates = [move for move in candidates if move.move_type == MoveType.SEARCH]
        non_search_candidates = [move for move in candidates if move.move_type != MoveType.SEARCH]
        my_turns = board.player_worker.turns_left

        if my_turns <= 10:
            non_search_candidates = self._late_phase_filter_non_search(board, non_search_candidates)
        if my_turns <= 1:
            point_moves = [move for move in non_search_candidates if move.move_type != MoveType.PLAIN]
            if point_moves:
                non_search_candidates = point_moves

        root_state, context = self._build_search_context(board, belief, state)
        board_move: Move | None = None
        board_delta = float("-inf")
        if non_search_candidates:
            searcher = BitboardSearch(tt_max_entries=self.TT_MAX_ENTRIES, max_depth=self.SEARCH_MAX_DEPTH)
            board_move, board_delta, _, _ = searcher.rank_moves(
                root_state,
                non_search_candidates,
                TimeManager.tactical_search_budget(board, state, search_window),
                context,
            )
        if board_move is None and non_search_candidates:
            board_move = sorted(non_search_candidates, key=self.move_sort_key)[0]
            board_delta = 0.0
        if board_move is None:
            return _persist_return(self._best_safe_non_search(board))
        board_gate = max(board_delta, self._board_gate_floor(board_move))

        best_search, search_ev, top_prob = self._best_search_candidate(search_candidates, belief)
        if best_search is None:
            return _persist_return(board_move)

        denial_value = self._opponent_denial_value(root_state, belief, state)
        score_diff = float(board.player_worker.get_points() - board.opponent_worker.get_points())
        lead_margin = self._lead_search_margin(score_diff)
        effective_board_gate = board_gate + lead_margin
        prob_floor = min(0.70, self.SEARCH_FLOOR_PROB + (self.lead_prob_floor_bonus if score_diff > 0.0 else 0.0))
        search_beats_board = search_ev > effective_board_gate
        threat_search = top_prob >= prob_floor and (
            search_ev + self.search_threat_w * denial_value > effective_board_gate
        )

        if (search_beats_board or threat_search) and board.is_valid_move(best_search):
            return _persist_return(best_search)
        return _persist_return(board_move if board.is_valid_move(board_move) else self._best_safe_non_search(board))
