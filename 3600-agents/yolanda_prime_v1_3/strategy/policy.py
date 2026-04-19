from __future__ import annotations

import time

import numpy as np

from game.board import Board
from game.enums import CARPET_POINTS_TABLE, BOARD_SIZE, Direction, MoveType, loc_after_direction
from game.move import Move

from . import adaptation
from .board_analysis import BoardAnalysis, INF
from .lookahead import Lookahead
from ..tracking.belief import BeliefEngine
from ..tracking.opponent_observation import OpponentCategory, infer_opponent_category
from ..infra.runtime_state import RuntimeState
from ..infra.time_manager import TimeManager


_REVERSE_DIR = {
    Direction.UP: Direction.DOWN,
    Direction.DOWN: Direction.UP,
    Direction.LEFT: Direction.RIGHT,
    Direction.RIGHT: Direction.LEFT,
}


class PolicyEngine:
    """Candidate generation and deterministic action selection policy."""

    def __init__(
        self,
        search_topk: int = 10,
        search_radius: int = 2,
        a: float = 1.40,
        b: float = 0.45,
        c: float = 1.20,
        d: float = 0.35,
        e: float = 1.00,
        f: float = 0.75,
        late_centrality_scale: float = 0.3,
        mid_lead_space_bonus: float = 0.5,
        g: float = 0.50, # Balanced fragmentation
        enable_lead_aware_centrality: bool = True,
        mid_lead_centrality_scale: float = 0.7,
        mid_trailing_centrality_scale: float = 1.2,
        opening_centrality_scale: float = 2.5,
        enable_threatened_cashout_bonus: bool = False,
        threatened_cashout_min_roll: int = 4,
        threatened_cashout_opp_dist: int = 3,
        threatened_cashout_bonus: float = 2.0,
        enable_opponent_chain_sabotage: bool = True,
        sabotage_min_chain_len: int = 3,
        sabotage_opp_dist: int = 3,
        sabotage_bonus: float = 3.5,
        enable_fast_search_shortcut: bool = False,
        fast_search_prob_threshold: float = 0.8,
        fast_search_max_carpet_points: float = 12.0,
    ) -> None:
        self.search_topk = search_topk
        self.search_radius = search_radius
        self.a = a
        self.b = b
        self.c = c
        self.d = d
        self.e = e
        self.f = f
        self.g = g
        # Yolanda2 fusion knobs are constructor-driven so ablations can be run via env, no code edits.
        self.enable_lead_aware_centrality = enable_lead_aware_centrality
        self.mid_lead_centrality_scale = mid_lead_centrality_scale
        self.mid_trailing_centrality_scale = mid_trailing_centrality_scale
        self.opening_centrality_scale = opening_centrality_scale
        self.late_centrality_scale = late_centrality_scale
        self.mid_lead_space_bonus = mid_lead_space_bonus

        self.enable_threatened_cashout_bonus = enable_threatened_cashout_bonus
        self.threatened_cashout_min_roll = threatened_cashout_min_roll
        self.threatened_cashout_opp_dist = threatened_cashout_opp_dist
        self.threatened_cashout_bonus = threatened_cashout_bonus

        self.enable_opponent_chain_sabotage = enable_opponent_chain_sabotage
        self.sabotage_min_chain_len = sabotage_min_chain_len
        self.sabotage_opp_dist = sabotage_opp_dist
        self.sabotage_bonus = sabotage_bonus

        self.enable_fast_search_shortcut = enable_fast_search_shortcut
        self.fast_search_prob_threshold = fast_search_prob_threshold
        self.fast_search_max_carpet_points = fast_search_max_carpet_points

        self._active_root_board: Board | None = None
        self._active_root_analysis: BoardAnalysis | None = None
        self._rollout_cache: dict[tuple, float] = {}
        self._opp_carpet_threat_cells: set[tuple[int, int]] = set()
        self._opp_carpet_threat_value: float = 0.0

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
        # Player search happened on turn N, opponent on turn N+1.
        # Process in chronological order so a later opponent hit correctly
        # overwrites any stale player-miss zeroing (old rat vs new rat).
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

    def _chain_score(self, board_after: Board, dest: tuple[int, int], *, analysis: BoardAnalysis | None = None) -> float:
        snap = analysis or self._analysis_for(board_after)
        best = 0.0
        for direction in (Direction.UP, Direction.DOWN, Direction.LEFT, Direction.RIGHT):
            prof = snap.chain_profile(dest, direction, include_occupied=True)
            if prof["straight_len"] < 2.0:
                continue
            # Blend immediate straight-line value with cached composite potential so
            # L/branch opportunities are visible without per-action rescans.
            composite = max(prof["immediate_value"], prof["composite_value"], 0.7 * prof["defer_value"])
            best = max(best, composite)
        return best

    def _risk_score(self, exit_count: int) -> float:
        risk = max(0.0, 1.0 - exit_count / 4.0)
        if exit_count <= 1:
            risk += 0.3
        return risk

    @staticmethod
    def _count_space_components(board: Board, analysis: BoardAnalysis | None = None) -> int:
        snap = analysis or BoardAnalysis(board)
        return snap.space_components

    def _analysis_for(self, board: Board) -> BoardAnalysis:
        if self._active_root_board is board and self._active_root_analysis is not None:
            return self._active_root_analysis
        return BoardAnalysis(board)

    def _fragmentation_score(
        self,
        board_before: Board,
        board_after: Board,
        action: Move,
        before_analysis: BoardAnalysis | None = None,
        after_analysis: BoardAnalysis | None = None,
    ) -> float:
        """Penalty for carpet actions that fragment the board's SPACE connectivity.

        Returns 0.0 for non-carpet actions.
        For carpets, returns (components_after - components_before) clipped to [0, inf).
        Higher = more fragmentation = worse.
        """
        if action.move_type != MoveType.CARPET:
            return 0.0
        comp_before = self._count_space_components(board_before, before_analysis)
        comp_after = self._count_space_components(board_after, after_analysis)
        frag = max(0.0, float(comp_after - comp_before))

        # Heuristic shortcut (§3.4): penalize center cross-sections that become fully non-SPACE after carpeting.
        src = board_before.player_worker.get_location()
        k = action.roll_length
        d = action.direction

        cur = src
        crossed_locs: list[tuple[int, int]] = []
        for _ in range(k):
            cur = loc_after_direction(cur, d)
            crossed_locs.append(cur)
        if crossed_locs:
            if d in (Direction.LEFT, Direction.RIGHT):
                row = crossed_locs[0][1]
                if 2 <= row <= 5:
                    before_has_space = any(board_before.get_cell((x, row)).name == "SPACE" for x in range(BOARD_SIZE))
                    after_has_space = any(board_after.get_cell((x, row)).name == "SPACE" for x in range(BOARD_SIZE))
                    if before_has_space and not after_has_space:
                        frag += 0.4 * k
            else:
                col = crossed_locs[0][0]
                if 2 <= col <= 5:
                    before_has_space = any(board_before.get_cell((col, y)).name == "SPACE" for y in range(BOARD_SIZE))
                    after_has_space = any(board_after.get_cell((col, y)).name == "SPACE" for y in range(BOARD_SIZE))
                    if before_has_space and not after_has_space:
                        frag += 0.4 * k
        return frag

    @staticmethod
    def _is_walkable_plain_cell(board: Board, loc: tuple[int, int], *, include_occupied: bool = False) -> bool:
        """Walkable for plain-step pathing: SPACE/CARPET; workers excluded unless include_occupied."""
        if not board.is_valid_cell(loc):
            return False
        if not include_occupied and loc in {board.player_worker.get_location(), board.opponent_worker.get_location()}:
            return False
        cell_name = board.get_cell(loc).name
        return cell_name in {"SPACE", "CARPET"}

    @staticmethod
    def _neighbors(loc: tuple[int, int]) -> tuple[tuple[int, int], tuple[int, int], tuple[int, int], tuple[int, int]]:
        x, y = loc
        return ((x, y + 1), (x, y - 1), (x + 1, y), (x - 1, y))

    def _count_plain_exits(
        self,
        board: Board,
        loc: tuple[int, int],
        *,
        exclude: set[tuple[int, int]] | None = None,
    ) -> int:
        """Count cardinal exits through plain-walkable cells.

        Exits follow the movement constraints from §6: not blocked, not primed, not occupied.
        """
        blocked = exclude or set()
        count = 0
        for nxt in self._neighbors(loc):
            if nxt in blocked:
                continue
            if self._is_walkable_plain_cell(board, nxt):
                count += 1
        return count

    def _single_plain_exit(
        self,
        board: Board,
        loc: tuple[int, int],
        *,
        exclude: set[tuple[int, int]] | None = None,
    ) -> tuple[int, int] | None:
        blocked = exclude or set()
        exits = [nxt for nxt in self._neighbors(loc) if nxt not in blocked and self._is_walkable_plain_cell(board, nxt)]
        if len(exits) != 1:
            return None
        return exits[0]

    def _adjacent_primed_chain_len(self, board: Board, entry: tuple[int, int], direction: Direction) -> int:
        """Length of contiguous primed chain adjacent to entry in direction."""
        cur = entry
        k = 0
        for _ in range(BOARD_SIZE - 1):
            cur = loc_after_direction(cur, direction)
            if not board.is_valid_cell(cur):
                break
            if board.get_cell(cur).name != "PRIMED":
                break
            k += 1
        return k

    def _entry_chain_lengths(
        self,
        board: Board,
        min_chain_len: int = 3,
        *,
        include_occupied: bool = False,
        analysis: BoardAnalysis | None = None,
    ) -> dict[tuple[int, int], int]:
        """Map walkable carpet-entry cells to best adjacent primed-chain length."""
        snap = analysis or self._analysis_for(board)
        entries = snap.entry_map_for(min_chain_len=min_chain_len, include_occupied=include_occupied)
        return {snap.loc_from_index(idx): k for idx, (k, _) in entries.items()}

    def _shortest_walkable_distance_to_entry(
        self,
        board: Board,
        start: tuple[int, int],
        entries: set[tuple[int, int]],
        *,
        analysis: BoardAnalysis | None = None,
    ) -> int | None:
        """Shortest path through plain-walkable cells to any entry cell."""
        if not entries:
            return None
        snap = analysis or self._analysis_for(board)
        start_idx = snap.index_from_loc(start)
        best = INF
        for loc in entries:
            d = snap.dist(start_idx, snap.index_from_loc(loc))
            if d < best:
                best = d
        if best >= INF:
            return None
        return best

    def _reachable_best_chain_value(
        self,
        board: Board,
        start: tuple[int, int],
        min_chain_len: int = 3,
        *,
        analysis: BoardAnalysis | None = None,
    ) -> float:
        """Best carpet value among reachable entry cells."""
        snap = analysis or self._analysis_for(board)
        start_idx = snap.index_from_loc(start)
        if min_chain_len == 3:
            return snap.reachable_best_chain_value(start_idx)

        entries = snap.entry_map_for(min_chain_len=min_chain_len, include_occupied=False)
        if not entries:
            return 0.0

        best = 0.0
        for e_idx, (k, _) in entries.items():
            if snap.dist(start_idx, e_idx) < INF:
                best = max(best, float(CARPET_POINTS_TABLE[min(k, 7)]))
        return best

    def _spatial_potential(self, board: Board, start: tuple[int, int], radius: int = 3) -> float:
        """Count reachable SPACE cells within a fixed radius (§3.6)."""
        visited = {start}
        queue = [(start, 0)]
        count = 0
        qidx = 0
        while qidx < len(queue):
            cur, dist = queue[qidx]
            qidx += 1
            if dist >= radius:
                continue
            for nxt in self._neighbors(cur):
                if nxt in visited:
                    continue
                if not board.is_valid_cell(nxt):
                    continue
                if board.get_cell(nxt).name == "SPACE":
                    count += 1
                if board.get_cell(nxt).name in ("SPACE", "CARPET"):
                    visited.add(nxt)
                    queue.append((nxt, dist + 1))
        return float(count)

    # ------------------------------------------------------------------
    # §7.2  Phase-dependent coefficient modulation
    # ------------------------------------------------------------------

    @staticmethod
    def _get_phase(turns_left: int) -> str:
        if turns_left > 28:
            return "opening"
        if turns_left > 10:
            return "mid"
        return "late"

    @staticmethod
    def _phase_multipliers(phase: str) -> tuple[float, float, float, float, float]:
        """Return (mult_a, mult_b, mult_c, mult_d, mult_f)."""
        if phase == "opening":
            # Restoration of v1.2 pacing: prioritizing immediate points (mult_a=1.2)
            # and solid setup (mult_c=1.5) to maintain match pressure.
            return (1.2, 1.0, 1.5, 0.4, 1.0)
        if phase == "mid":
            return (1.0, 0.8, 1.5, 0.8, 1.0)
        return (1.5, 0.3, 0.5, 1.2, 0.5)

    # ------------------------------------------------------------------
    # §2.1-2.3  Prime direction optimisation
    # ------------------------------------------------------------------

    @staticmethod
    def _contiguous_primeable_ahead(board: Board, pos: tuple[int, int], direction: Direction) -> int:
        """Count SPACE cells ahead of *pos* in *direction*."""
        count = 0
        cur = pos
        for _ in range(BOARD_SIZE - 1):
            cur = loc_after_direction(cur, direction)
            if not board.is_valid_cell(cur):
                break
            if board.get_cell(cur).name != "SPACE":
                break
            count += 1
        return count

    def _positional_chain_potential(self, board: Board, loc: tuple[int, int]) -> float:
        """Score based on longest open chain (SPACE) starting from this location."""
        best_ahead = 0
        for direction in (Direction.UP, Direction.DOWN, Direction.LEFT, Direction.RIGHT):
            ahead = self._contiguous_primeable_ahead(board, loc, direction)
            best_ahead = max(best_ahead, ahead)
        return float(best_ahead)

    @staticmethod
    def _chain_alignment_behind(board: Board, src: tuple[int, int], direction: Direction) -> int:
        """Count contiguous PRIMED cells behind *src* in reverse of *direction*."""
        rev = _REVERSE_DIR[direction]
        count = 0
        cur = src
        for _ in range(BOARD_SIZE - 1):
            cur = loc_after_direction(cur, rev)
            if not board.is_valid_cell(cur):
                break
            if board.get_cell(cur).name != "PRIMED":
                break
            count += 1
        return count

    def _prime_future_potential(self, board: Board, action: Move) -> float:
        """Fallback prime heuristic: chain continuation + perpendicular expansion potential."""
        if action.move_type != MoveType.PRIME:
            return float("-inf")
        src = board.player_worker.get_location()
        dest = loc_after_direction(src, action.direction)
        if not board.is_valid_cell(dest):
            return float("-inf")
        if not board.is_valid_move(action):
            return float("-inf")

        forward = self._contiguous_primeable_ahead(board, dest, action.direction)
        alignment = self._chain_alignment_behind(board, src, action.direction)

        # perpendicular_extension_potential from opening heuristic.
        if action.direction in (Direction.UP, Direction.DOWN):
            perp_a, perp_b = Direction.LEFT, Direction.RIGHT
        else:
            perp_a, perp_b = Direction.UP, Direction.DOWN
        perp = max(
            self._contiguous_primeable_ahead(board, dest, perp_a),
            self._contiguous_primeable_ahead(board, dest, perp_b),
        )

        return 3.0 * forward + 2.5 * alignment + 0.5 * perp

    def _prime_direction_bonus(
        self, board: Board, action: Move, dest: tuple[int, int], *, analysis: BoardAnalysis | None = None
    ) -> float:
        """Extra carpet-setup credit for prime moves with chain-building potential."""
        if action.move_type != MoveType.PRIME:
            return 0.0
        src = board.player_worker.get_location()
        ahead = self._contiguous_primeable_ahead(board, dest, action.direction)
        alignment = self._chain_alignment_behind(board, src, action.direction)

        opp_loc = board.opponent_worker.get_location()
        opp_dist = abs(dest[0] - opp_loc[0]) + abs(dest[1] - opp_loc[1])
        opp_proximity = max(0.0, 3.0 - opp_dist)

        base = max(0.0, (3.0 * ahead + 2.5 * alignment - 0.3 * opp_proximity) / 5.5)

        opp_chains = self._opponent_reachable_chains(board, analysis=analysis)
        if opp_chains:
            opp_entry_locs = set(opp_chains.keys())
            chain_end = dest
            for _ in range(ahead):
                chain_end = loc_after_direction(chain_end, action.direction)
            for nxt in self._neighbors(chain_end):
                if board.is_valid_cell(nxt) and nxt in opp_entry_locs:
                    base += 1.5
                    break

        return base

    # ------------------------------------------------------------------
    # §3.2  Carpet timing logic
    # ------------------------------------------------------------------

    def _can_extend_chain(self, board: Board, carpet_action: Move) -> bool:
        """True if one legal prime turn can increase this adjacent chain by at least 1."""
        if carpet_action.move_type != MoveType.CARPET:
            return False
        d = carpet_action.direction
        k = carpet_action.roll_length
        # Extend from near-end by priming the current entry square and stepping backward.
        prime_ext = Move.prime(_REVERSE_DIR[d])
        if not board.is_valid_move(prime_ext):
            return False
        board_after_prime = board.forecast_move(prime_ext, check_ok=True)
        if board_after_prime is None:
            return False
        new_loc = board_after_prime.player_worker.get_location()
        return self._adjacent_primed_chain_len(board_after_prime, new_loc, d) >= (k + 1)

    @staticmethod
    def _next_tier_delta(k: int) -> float:
        if k >= 7:
            return 0.0
        if k < 1:
            return 0.0
        return float(CARPET_POINTS_TABLE[k + 1] - CARPET_POINTS_TABLE[k])

    def _extension_cell(self, board: Board, carpet_action: Move) -> tuple[int, int] | None:
        if carpet_action.move_type != MoveType.CARPET:
            return None
        # One-turn chain extension cell is the legal destination of prime(reverse(direction)).
        ext = loc_after_direction(board.player_worker.get_location(), _REVERSE_DIR[carpet_action.direction])
        if not board.is_valid_move(Move.prime(_REVERSE_DIR[carpet_action.direction])):
            return None
        return ext

    def _extension_is_contested(self, board: Board, carpet_action: Move) -> bool:
        ext = self._extension_cell(board, carpet_action)
        if ext is None:
            return False
        opp = board.opponent_worker.get_location()
        return abs(ext[0] - opp[0]) + abs(ext[1] - opp[1]) <= 1

    def _carpet_path_cells(self, board: Board, action: Move) -> tuple[tuple[int, int], ...]:
        if action.move_type != MoveType.CARPET:
            return tuple()
        cur = board.player_worker.get_location()
        cells: list[tuple[int, int]] = []
        for _ in range(action.roll_length):
            cur = loc_after_direction(cur, action.direction)
            if not board.is_valid_cell(cur):
                break
            cells.append(cur)
        return tuple(cells)

    def _has_carpet_break(self, board: Board, target_cells: set[tuple[int, int]], *, enemy: bool) -> bool:
        if not target_cells:
            return False
        src = board.opponent_worker.get_location() if enemy else board.player_worker.get_location()
        for mv in board.get_valid_moves(enemy=enemy, exclude_search=True):
            if mv.move_type != MoveType.CARPET or mv.roll_length < 2:
                continue
            cur = src
            for _ in range(mv.roll_length):
                cur = loc_after_direction(cur, mv.direction)
                if cur in target_cells:
                    return True
        return False

    def _enemy_two_ply_break_rate(self, board: Board, target_cells: set[tuple[int, int]]) -> float:
        if not target_cells:
            return 0.0
        enemy_moves = [
            mv for mv in board.get_valid_moves(enemy=True, exclude_search=True)
            if mv.move_type in (MoveType.PLAIN, MoveType.PRIME)
        ]
        if not enemy_moves:
            return 0.0

        checked = 0
        break_count = 0
        for mv in sorted(enemy_moves, key=self.move_sort_key):
            if checked >= 8:
                break
            board_opp = board.get_copy()
            board_opp.reverse_perspective()
            if not board_opp.apply_move(mv, check_ok=True):
                continue
            checked += 1
            if self._has_carpet_break(board_opp, target_cells, enemy=False):
                break_count += 1
        if checked <= 0:
            return 0.0
        return break_count / checked

    def _chain_survival_summary(
        self,
        board: Board,
        action: Move,
        *,
        deep_eval: bool = False,
    ) -> tuple[float, bool, float]:
        if action.move_type != MoveType.CARPET:
            return 1.0, False, 0.0

        chain_cells = set(self._carpet_path_cells(board, action))
        if not chain_cells:
            return 1.0, False, 0.0

        opp_loc = board.opponent_worker.get_location()
        min_dist = min(abs(cell[0] - opp_loc[0]) + abs(cell[1] - opp_loc[1]) for cell in chain_cells)
        if min_dist <= 1:
            survival = 0.30
        elif min_dist == 2:
            survival = 0.50
        elif min_dist == 3:
            survival = 0.66
        else:
            survival = 0.82

        immediate_break = self._has_carpet_break(board, chain_cells, enemy=True)
        if immediate_break:
            survival = min(survival, 0.15)

        two_ply_break = 0.0
        if deep_eval and not immediate_break:
            two_ply_break = self._enemy_two_ply_break_rate(board, chain_cells)
            survival *= max(0.20, 1.0 - 0.75 * two_ply_break)

        return float(max(0.0, min(1.0, survival))), immediate_break, two_ply_break

    def _carpet_timing_adjustment(
        self,
        board: Board,
        action: Move,
        turns_left: int,
        *,
        analysis: BoardAnalysis | None = None,
        deep_eval: bool = False,
    ) -> float:
        """Cashout gate: compare carpet-now EV vs defer EV under disruption risk."""
        if action.move_type != MoveType.CARPET:
            return 0.0
        k = action.roll_length
        if k <= 1:
            return -100.0
        snap = analysis or self._analysis_for(board)
        src = board.player_worker.get_location()
        prof = snap.chain_profile(src, action.direction, include_occupied=True)

        now_value = float(CARPET_POINTS_TABLE[min(k, 7)])
        can_extend = self._can_extend_chain(board, action)
        next_turn_value = float(CARPET_POINTS_TABLE[min(k + 1, 7)]) if can_extend else now_value
        composite_value = max(now_value, prof["composite_value"])
        defer_target = max(composite_value, prof["defer_value"], next_turn_value)

        survival, immediate_break, two_ply_break = self._chain_survival_summary(
            board,
            action,
            deep_eval=deep_eval,
        )
        # If defer fails, we assume partial salvage rather than zero because some
        # tactical denial or shorter carpets can still remain available.
        ev_wait = survival * defer_target + (1.0 - survival) * max(0.0, now_value - 2.0)
        threatened = immediate_break or two_ply_break >= 0.35 or survival < 0.55

        # Improvement: Reward deferring short carpets if they can be extended and aren't threatened.
        if k == 2 and turns_left > 15 and not threatened and can_extend:
            # Instead of a hard penalty, we reduce the score of 'now' compared to 'wait'
            return -1.5

        cashout_floor = 6.0 if turns_left > 4 else 4.0
        if threatened and now_value >= cashout_floor:
            return 3.0 + 0.2 * now_value

        if turns_left <= k + 1:
            return 2.0 + 0.15 * now_value

        if now_value + 0.6 >= ev_wait:
            return 0.8 + 0.1 * now_value

        return -(0.6 + 0.25 * (ev_wait - now_value))

    # ------------------------------------------------------------------
    # §6.2  Corridor trap detection
    # ------------------------------------------------------------------

    def _corridor_trap_penalty(self, board_after: Board, dest: tuple[int, int], exit_count: int) -> float:
        """Extra risk penalty when the single exit leads to another dead end."""
        if exit_count > 1:
            return 0.0
        if exit_count <= 0:
            return 0.5
        single_exit = self._single_plain_exit(board_after, dest)
        if single_exit is None:
            return 0.5
        exits_of_exit = self._count_plain_exits(board_after, single_exit, exclude={dest})
        if exits_of_exit <= 1:
            return 0.4
        return 0.0

    def _is_corridor_trap_move(self, board: Board, action: Move) -> bool:
        """True when action lands in a corridor trap (§6.2)."""
        board_after = board.forecast_move(action, check_ok=True)
        if board_after is None:
            return False
        dest = self._destination(board, action)
        exit_count = self._count_plain_exits(board_after, dest)
        if exit_count != 1:
            return False
        single_exit = self._single_plain_exit(board_after, dest)
        if single_exit is None:
            return False
        exits_of_exit = self._count_plain_exits(board_after, single_exit, exclude={dest})
        return exits_of_exit <= 1

    def _prime_enables_next_turn_carpet(self, board: Board, action: Move, min_roll: int = 3) -> bool:
        if action.move_type != MoveType.PRIME:
            return False
        bd_after = board.forecast_move(action, check_ok=True)
        if bd_after is None:
            return False
        for mv in bd_after.get_valid_moves(exclude_search=True):
            if mv.move_type == MoveType.CARPET and mv.roll_length >= min_roll:
                return True
        return False

    def _nearest_primable_corridor_distance(
        self,
        board: Board,
        start: tuple[int, int],
        *,
        analysis: BoardAnalysis | None = None,
    ) -> int | None:
        snap = analysis or self._analysis_for(board)
        return snap.dist_to_nearest_primable(start)

    def _no_good_move_fallback(
        self,
        board: Board,
        candidates: list[Move],
        *,
        analysis: BoardAnalysis | None = None,
    ) -> Move:
        """§8.1 fallback order when all non-search choices are weak and search EV is non-positive."""
        snap = analysis or self._analysis_for(board)
        non_search = [m for m in candidates if m.move_type != MoveType.SEARCH]
        primes = [m for m in non_search if m.move_type == MoveType.PRIME]
        prime_best: tuple[float, tuple, Move] | None = None
        if primes:
            scored_primes: list[tuple[float, tuple, Move]] = []
            for m in primes:
                scored_primes.append((self._prime_future_potential(board, m), self.move_sort_key(m), m))
            scored_primes.sort(key=lambda x: (-x[0], x[1]))
            prime_best = scored_primes[0]

        carpets = [m for m in non_search if m.move_type == MoveType.CARPET and m.roll_length >= 2]
        if carpets:
            scored_carpet: list[tuple[float, tuple, Move]] = []
            emergency = self._opp_carpet_threat_value >= 6.0
            for m in carpets:
                guaranteed = float(CARPET_POINTS_TABLE[min(m.roll_length, 7)])
                denial = self._denial_carpet_bonus(board, m)
                survival, immediate_break, _ = self._chain_survival_summary(board, m, deep_eval=False)
                emergency_cashout = 0.0
                if emergency and guaranteed >= 4.0:
                    emergency_cashout = 2.0
                if immediate_break and guaranteed >= 4.0:
                    emergency_cashout += 1.5
                scored = guaranteed + denial + emergency_cashout + (1.0 - survival) * 0.8 * guaranteed
                scored_carpet.append((scored, self.move_sort_key(m), m))
            scored_carpet.sort(key=lambda x: (-x[0], x[1]))
            best_carpet = scored_carpet[0]
            prime_ref = float("-inf") if prime_best is None else prime_best[0]
            if emergency or best_carpet[0] >= max(4.0, prime_ref + 1.5):
                return best_carpet[2]

        if prime_best is not None:
            return prime_best[2]

        plains = [m for m in non_search if m.move_type == MoveType.PLAIN]
        if plains:
            current = board.player_worker.get_location()
            base_dist = self._nearest_primable_corridor_distance(board, current, analysis=snap)
            scored: list[tuple[int, tuple, Move]] = []
            for m in plains:
                dest = self._destination(board, m)
                d = self._nearest_primable_corridor_distance(board, dest, analysis=snap)
                # Prefer lower distance; unreachable gets large sentinel.
                d_eff = 999 if d is None else d
                # Prefer strict improvement over current distance when available.
                if base_dist is not None and d is not None and d < base_dist:
                    d_eff -= 1
                scored.append((d_eff, self.move_sort_key(m), m))
            scored.sort(key=lambda x: (x[0], x[1]))
            return scored[0][2]

        if non_search:
            non_search.sort(key=self.move_sort_key)
            return non_search[0]
        return self._best_safe_non_search(board)

    def _carpet_landing_adjustment(self, board_after: Board, action: Move, dest: tuple[int, int]) -> float:
        """Reward carpet landings that preserve immediate mobility and prime restart options."""
        if action.move_type != MoveType.CARPET:
            return 0.0
        exits = self._count_plain_exits(board_after, dest)
        space_neighbors = sum(
            1 for nxt in self._neighbors(dest)
            if board_after.is_valid_cell(nxt) and board_after.get_cell(nxt).name == "SPACE"
        )
        has_space_exit = space_neighbors > 0
        bonus = 0.0
        if exits >= 3 and has_space_exit:
            bonus += 0.8
        if exits <= 1:
            bonus -= 1.2
        if not has_space_exit:
            bonus -= 0.8
        bonus += 0.5 * space_neighbors
        return bonus

    def _high_value_deny_bonus(
        self,
        board: Board,
        action: Move,
        dest: tuple[int, int],
        *,
        analysis: BoardAnalysis | None = None,
    ) -> float:
        """Bonus for 0-1 turn blocks on opponent carpet entries for L5+ chains (§5.4)."""
        if action.move_type not in (MoveType.PLAIN, MoveType.PRIME):
            return 0.0

        snap = analysis or self._analysis_for(board)
        entries = snap.entry_map_for(min_chain_len=5, include_occupied=True)
        if not entries:
            return 0.0

        opp = board.opponent_worker.get_location()
        opp_idx = snap.index_from_loc(opp)
        threatened: set[tuple[int, int]] = set()
        if opp_idx in entries:
            threatened.add(opp)
        for nxt in self._neighbors(opp):
            if board.is_valid_cell(nxt) and snap.index_from_loc(nxt) in entries and self._is_walkable_plain_cell(board, nxt):
                threatened.add(nxt)

        if dest in threatened:
            return 2.0
        return 0.0

    def _opponent_chain_threat_bonus(
        self,
        board: Board,
        action: Move,
        dest: tuple[int, int],
        *,
        analysis: BoardAnalysis | None = None,
    ) -> float:
        """Bounded anti-setup denial bonus when opponent can access L3+ entry cells quickly."""
        if action.move_type not in (MoveType.PLAIN, MoveType.PRIME, MoveType.CARPET):
            return 0.0

        snap = analysis or self._analysis_for(board)
        entries = snap.entry_map_for(min_chain_len=self.sabotage_min_chain_len, include_occupied=True)
        if not entries:
            return 0.0

        opp_loc = board.opponent_worker.get_location()
        threatened_entries = {
            snap.loc_from_index(entry_idx)
            for entry_idx in entries
            if snap.dist(opp_loc, entry_idx) <= self.sabotage_opp_dist
        }
        if not threatened_entries:
            return 0.0

        if action.move_type == MoveType.CARPET:
            return self._preemptive_carpet_bonus(board, action, analysis=snap)

        if dest in threatened_entries:
            return self.sabotage_bonus
        if any(nxt in threatened_entries for nxt in self._neighbors(dest) if board.is_valid_cell(nxt)):
            return self.sabotage_bonus
        return 0.0

    def _opponent_reachable_chains(
        self,
        board: Board,
        *,
        analysis: BoardAnalysis | None = None,
    ) -> dict[tuple[int, int], tuple[int, int]]:
        """Map opponent-reachable carpet entry locs to (chain_len, opp_bfs_distance).

        Uses the board's existing entry map; filters to entries the opponent
        can reach via walkable cells within BFS distance 3.
        """
        snap = analysis or self._analysis_for(board)
        entries = snap.entry_map_for(min_chain_len=2, include_occupied=True)
        if not entries:
            return {}

        opp_loc = board.opponent_worker.get_location()
        result: dict[tuple[int, int], tuple[int, int]] = {}
        for entry_idx, (chain_len, _direction) in entries.items():
            d = snap.dist(opp_loc, entry_idx)
            if d <= 3:
                result[snap.loc_from_index(entry_idx)] = (chain_len, d)
        return result

    def _preemptive_carpet_bonus(
        self,
        board: Board,
        action: Move,
        *,
        analysis: BoardAnalysis | None = None,
    ) -> float:
        """Bonus for carpet moves that destroy cells in an opponent-reachable primed chain."""
        if action.move_type != MoveType.CARPET:
            return 0.0

        opp_chains = self._opponent_reachable_chains(board, analysis=analysis)
        if not opp_chains:
            return 0.0

        opp_chain_cells: set[tuple[int, int]] = set()
        snap = analysis or self._analysis_for(board)
        for entry_loc, (chain_len, _opp_dist) in opp_chains.items():
            entry_idx = snap.index_from_loc(entry_loc)
            entries_full = snap.entry_map_for(min_chain_len=2, include_occupied=True)
            if entry_idx not in entries_full:
                continue
            _k, direction = entries_full[entry_idx]
            cur = entry_loc
            for _ in range(chain_len):
                cur = loc_after_direction(cur, direction)
                if not board.is_valid_cell(cur):
                    break
                if board.get_cell(cur).name == "PRIMED":
                    opp_chain_cells.add(cur)

        if not opp_chain_cells:
            return 0.0

        src = board.player_worker.get_location()
        cur = src
        destroyed = 0
        best_denied_chain = 0
        for _ in range(action.roll_length):
            cur = loc_after_direction(cur, action.direction)
            if cur in opp_chain_cells:
                destroyed += 1
                for entry_loc, (chain_len, _) in opp_chains.items():
                    e_idx = snap.index_from_loc(entry_loc)
                    entries_full = snap.entry_map_for(min_chain_len=2, include_occupied=True)
                    if e_idx in entries_full:
                        best_denied_chain = max(best_denied_chain, chain_len)

        if destroyed == 0:
            return 0.0

        return 3.0 + 1.0 * max(0, best_denied_chain - 2)

    def _compute_opp_carpet_threats(self, board: Board) -> tuple[set[tuple[int, int]], float]:
        """Compute primed cells the opponent can carpet immediately or within 1 step."""
        opp_loc = board.opponent_worker.get_location()
        cells: set[tuple[int, int]] = set()
        best_val = 0.0

        for mv in board.get_valid_moves(enemy=True, exclude_search=True):
            if mv.move_type != MoveType.CARPET or mv.roll_length < 2:
                continue
            pts = float(CARPET_POINTS_TABLE[min(mv.roll_length, 7)])
            best_val = max(best_val, pts)
            cur = opp_loc
            for _ in range(mv.roll_length):
                cur = loc_after_direction(cur, mv.direction)
                cells.add(cur)

        for adj in self._neighbors(opp_loc):
            if not self._is_walkable_plain_cell(board, adj):
                continue
            for d in (Direction.UP, Direction.DOWN, Direction.LEFT, Direction.RIGHT):
                k = self._adjacent_primed_chain_len(board, adj, d)
                if k >= 2:
                    pts = float(CARPET_POINTS_TABLE[min(k, 7)])
                    best_val = max(best_val, pts)
                    cur = adj
                    for _ in range(k):
                        cur = loc_after_direction(cur, d)
                        cells.add(cur)

        return cells, best_val

    def _denial_carpet_bonus(self, board: Board, action: Move) -> float:
        """Bonus for carpeting tiles the opponent could carpet on their next turn(s)."""
        if action.move_type != MoveType.CARPET or action.roll_length < 2:
            return 0.0
        if not self._opp_carpet_threat_cells or self._opp_carpet_threat_value < 4.0:
            return 0.0

        src = board.player_worker.get_location()
        cur = src
        denied = 0
        for _ in range(action.roll_length):
            cur = loc_after_direction(cur, action.direction)
            if cur in self._opp_carpet_threat_cells:
                denied += 1

        if denied == 0:
            return 0.0

        return 3.0 + 0.4 * self._opp_carpet_threat_value

    def _cluster_contention_bonus(
        self,
        board: Board,
        action: Move,
        dest: tuple[int, int],
        *,
        analysis: BoardAnalysis | None = None,
    ) -> float:
        """Ownership-agnostic primed-cluster contention bonus using access-time gaps."""
        snap = analysis or self._analysis_for(board)
        clusters = snap.primed_cluster_profiles()
        if not clusters:
            return 0.0

        dest_idx = snap.index_from_loc(dest)
        path_cells = self._carpet_path_cells(board, action)
        path_indices = {snap.index_from_loc(loc) for loc in path_cells}
        bonus = 0.0

        for cluster in clusters:
            cluster_value = float(cluster["cluster_value"])
            if cluster_value < 4.0:
                continue
            threat_gap = float(cluster["threat_gap"])
            leverage = float(cluster["disruption_leverage"])
            cluster_cells = set(cluster["cells"])
            cluster_entries = set(cluster["entries"])

            if action.move_type == MoveType.CARPET and path_indices and path_indices.intersection(cluster_cells):
                if threat_gap >= 0.0:
                    bonus += 1.5 + 0.25 * leverage
                else:
                    bonus += 0.6
                continue

            if action.move_type in (MoveType.PLAIN, MoveType.PRIME) and dest_idx in cluster_entries:
                if threat_gap >= 0.0:
                    bonus += 1.0 + 0.2 * leverage
                else:
                    bonus += 0.4

        return min(4.0, bonus)

    def _prime_adjacent_opponent_blocks_approach(
        self,
        board: Board,
        board_after: Board,
        src: tuple[int, int],
        dest: tuple[int, int],
        *,
        before_analysis: BoardAnalysis | None = None,
        after_analysis: BoardAnalysis | None = None,
    ) -> bool:
        """Veto risky near-opponent primes that sever our nearby carpet access (§2.4 rule #3)."""
        opp = board.opponent_worker.get_location()
        if abs(dest[0] - opp[0]) + abs(dest[1] - opp[1]) != 1:
            return False

        snap_before = before_analysis or self._analysis_for(board)
        snap_after = after_analysis or self._analysis_for(board_after)

        before_entries = set(self._entry_chain_lengths(board, min_chain_len=3, analysis=snap_before).keys())
        if not before_entries:
            return False
        after_entries = set(self._entry_chain_lengths(board_after, min_chain_len=3, analysis=snap_after).keys())

        before_dist = self._shortest_walkable_distance_to_entry(board, src, before_entries, analysis=snap_before)
        after_dist = self._shortest_walkable_distance_to_entry(board_after, dest, after_entries, analysis=snap_after)
        if before_dist is None:
            return False
        return before_dist <= 2 and (after_dist is None or after_dist > 2)

    # ------------------------------------------------------------------
    # §8.3-8.4  Score-pressure coefficient modulation
    # ------------------------------------------------------------------

    @staticmethod
    def _apply_score_pressure(board: Board, state: RuntimeState) -> None:
        """Shift effective coefficients according to score differential."""
        my_score = board.player_worker.get_points()
        opp_score = board.opponent_worker.get_points()
        turns_left = board.player_worker.turns_left
        if turns_left <= 0:
            return
        delta = my_score - opp_score
        if delta < 0:
            required_rate = abs(delta) / turns_left
            if required_rate >= 2.0:
                state.effective_a *= 1.15
                state.effective_c *= 0.70
            elif required_rate >= 1.0:
                state.effective_a *= 1.05
                state.effective_c *= 0.85
        elif delta > 0:
            if delta > 3 * turns_left:
                state.effective_f *= 1.3
            elif delta > turns_left:
                state.effective_d *= 1.2

    def _adapted_coefficients(
        self,
        state: RuntimeState,
        base_a: float,
        base_c: float,
        base_d: float,
        base_f: float,
    ) -> tuple[float, float, float, float]:
        """Apply opponent adaptation using the provided bases (phase-first integration)."""
        if (
            state.plies_as_player < 2
            or state.plies_as_player % 2 != 0
            or state.observed_turns < adaptation.MIN_OBSERVED_TURNS
        ):
            return base_a, base_c, base_d, base_f

        hist = {
            OpponentCategory.PLAIN: 0,
            OpponentCategory.PRIME: 0,
            OpponentCategory.CARPET: 0,
            OpponentCategory.SEARCH: 0,
        }
        mobilities: list[int] = []
        low_exit_n = 0
        typed = 0
        for c, m in state.opp_turn_buffer:
            if c is None:
                continue
            hist[c] += 1
            typed += 1
            mobilities.append(m)
            if c != OpponentCategory.SEARCH and m <= 2:
                low_exit_n += 1
        if typed <= 0:
            return base_a, base_c, base_d, base_f

        mean_mob = sum(mobilities) / len(mobilities) if mobilities else 0.0
        low_exit_rate = (low_exit_n / len(mobilities)) if mobilities else 0.0
        ent_norm = adaptation.normalized_entropy_category_counts(hist)
        state.behavior_entropy_norm = ent_norm

        conf = adaptation.compute_confidence(state.observed_turns, ent_norm)
        raw = adaptation.pattern_raw_deltas(
            category_hist=hist,
            total_typed=typed,
            mean_opp_mobility=mean_mob,
            low_exit_rate=low_exit_rate,
            search_attempts=state.opp_search_attempts,
            search_correct=state.opp_search_correct,
        )
        return adaptation.apply_adaptation(
            conf,
            raw,
            base_a=base_a,
            base_c=base_c,
            base_d=base_d,
            base_f=base_f,
        )

    # ------------------------------------------------------------------

    @staticmethod
    def _continuation_tiebreak(action: Move, state: RuntimeState) -> float:
        """Tie-break boost for chain-continuation directionality (§7.3)."""
        last = state.last_own_move
        if last is None:
            return 0.0
        if action.move_type not in (MoveType.PRIME, MoveType.CARPET):
            return 0.0
        if last.move_type not in (MoveType.PRIME, MoveType.CARPET):
            return 0.0
        return 1.0 if action.direction == last.direction else 0.0

    def _score_position_lite(self, board: Board, loc: tuple[int, int], belief_vec: np.ndarray | None = None) -> float:
        """Lightweight positional evaluation for minimax search.
        Aligned with full PolicyEngine weights but optimized for recursion speed.
        """
        # 1. Mobility (Resist pinning)
        exits = self._count_plain_exits(board, loc)
        if exits == 0:
            return -10.0
        
        # 2. Centrality (Control the board)
        center_dist = abs(loc[0] - 3.5) + abs(loc[1] - 3.5)
        centrality = 1.0 - center_dist / 7.0
        
        # 3. Chain/Carpet Potential (Offensive threat)
        max_chain = 0
        for d in Direction:
            k = self._adjacent_primed_chain_len(board, loc, d)
            if k > max_chain:
                max_chain = k
        chain_val = 0.0
        if max_chain >= 2:
            chain_val = float(CARPET_POINTS_TABLE[min(max_chain, 7)])
            
        # 4. Rat Proximity (Strategic focus)
        rat_val = 0.0
        if belief_vec is not None:
            max_idx = int(np.argmax(belief_vec))
            ry, rx = divmod(max_idx, BOARD_SIZE)
            dist = abs(loc[0] - rx) + abs(loc[1] - ry)
            rat_val = max(0.0, 3.0 - 0.5 * dist)
            # Extra bonus for directly landing on most likely rat cell
            if loc == (rx, ry):
                rat_val += 2.0

        # Weighted sum matching the 'pacing' of the main policy
        return (exits * 0.5) + (centrality * 1.5) + (chain_val * 0.8) + (rat_val * 1.0)

    def score_non_search(
        self,
        board: Board,
        action: Move,
        belief: BeliefEngine,
        state: RuntimeState,
        *,
        analysis: BoardAnalysis | None = None,
        board_after_analysis: BoardAnalysis | None = None,
        precomputed_board_after: Board | None = None,
        deep_eval: bool = False,
    ) -> tuple[float, dict[str, float]]:
        if action.move_type == MoveType.SEARCH:
            return float("-inf"), {"mobility": 0.0, "immediate": 0.0, "risk": 0.0, "continuation": 0.0}

        snap_before = analysis or self._analysis_for(board)
        board_after = precomputed_board_after or board.forecast_move(action, check_ok=True)
        if board_after is None:
            return float("-inf"), {"mobility": 0.0, "immediate": 0.0, "risk": 1.0, "continuation": 0.0}
        snap_after = board_after_analysis or BoardAnalysis(board_after)

        dest = self._destination(board, action)
        exit_count = self._count_plain_exits(board_after, dest)

        # Hard constraint §13.2 / §6.1: never enter a 0-exit position
        if exit_count == 0:
            return float("-inf"), {"mobility": 0.0, "immediate": 0.0, "risk": 1.3, "continuation": 0.0}

        immediate = 0.0
        if action.move_type == MoveType.PRIME:
            immediate = 1.0
        elif action.move_type == MoveType.CARPET:
            immediate = float(CARPET_POINTS_TABLE[action.roll_length])

        # Hard constraint §13.1 / §3.2: never carpet length 1
        if action.move_type == MoveType.CARPET and action.roll_length <= 1:
            return float("-inf"), {"mobility": 0.0, "immediate": immediate, "risk": 0.0, "continuation": 0.0}

        # Hard constraint §13.4: veto prime moves that make reachable best chains uncarpetable.
        if action.move_type == MoveType.PRIME:
            src_before = board.player_worker.get_location()
            before_best = self._reachable_best_chain_value(board, src_before, min_chain_len=3, analysis=snap_before)
            after_best = self._reachable_best_chain_value(board_after, dest, min_chain_len=3, analysis=snap_after)
            if before_best >= float(CARPET_POINTS_TABLE[3]) and after_best <= 0.0:
                return float("-inf"), {"mobility": 0.0, "immediate": immediate, "risk": 1.3, "continuation": 0.0}
            if self._prime_adjacent_opponent_blocks_approach(
                board,
                board_after,
                src_before,
                dest,
                before_analysis=snap_before,
                after_analysis=snap_after,
            ):
                return float("-inf"), {"mobility": float(exit_count), "immediate": immediate, "risk": 1.3, "continuation": 0.0}

        center_dist = abs(dest[0] - 3.5) + abs(dest[1] - 3.5)
        centrality = 1.0 - center_dist / 7.0
        phase = self._get_phase(board.player_worker.turns_left)
        my_score = board.player_worker.get_points()
        opp_score = board.opponent_worker.get_points()
        has_lead = my_score > opp_score

        if phase == "opening":
            centrality_scale = self.opening_centrality_scale
        elif phase == "mid":
            if self.enable_lead_aware_centrality:
                centrality_scale = self.mid_lead_centrality_scale if has_lead else self.mid_trailing_centrality_scale
            else:
                centrality_scale = 1.0
        else:
            centrality_scale = self.late_centrality_scale
        spatial = self._spatial_potential(board_after, dest, radius=3)
        
        # Improvement: favour locations that have long open space chains ahead for positioning.
        chain_potential = self._positional_chain_potential(board_after, dest)
        
        # Increased exit_count weight from 0.25 to 0.5 to strongly resist being pinned.
        position = (exit_count / 2.0) + 0.3 * centrality * centrality_scale + 0.04 * spatial + 0.12 * chain_potential
        
        # Improvement: Mobility Delta. If opponent has many more moves than us, penalize.
        opponent_moves = len(board_after.get_valid_moves(enemy=True, exclude_search=True))
        mobility_delta = float(exit_count - opponent_moves)
        mobility_penalty = 0.0
        if mobility_delta < -2.0:
            mobility_penalty = 0.4 * abs(mobility_delta + 2.0)
        
        if (
            self.enable_lead_aware_centrality
            and phase == "mid"
            and has_lead
            and board.get_cell(dest).name == "SPACE"
        ):
            position += self.mid_lead_space_bonus

        if action.move_type == MoveType.PLAIN:
            steps_to_entry = snap_after.dist_to_nearest_entry(dest)
            if steps_to_entry is not None:
                position += max(0.0, 2.0 - 0.5 * steps_to_entry)
            else:
                position -= 1.5

        if action.move_type == MoveType.PRIME:
            steps_to_entry = snap_after.dist_to_nearest_entry(dest)
            if steps_to_entry is not None and steps_to_entry <= 3:
                position += max(0.0, 1.5 - 0.5 * steps_to_entry)

        # --- Phase-Specific Behavior Adjustments ---
        phase_bonus = 0.0
        is_long_carpet = (action.move_type == MoveType.CARPET and action.roll_length >= 3)
        is_short_carpet = (action.move_type == MoveType.CARPET and action.roll_length == 2)

        if phase == "opening":
            # Encourage filling space and building chains early, discourage wasting turns on PLAIN
            if action.move_type == MoveType.PRIME:
                phase_bonus += 2.0
            elif is_long_carpet:
                phase_bonus += 5.5
            elif is_short_carpet:
                phase_bonus += 2.0
        elif phase == "mid":
            # Encourage cashing in and taking space
            if is_long_carpet:
                phase_bonus += 4.5
            elif is_short_carpet:
                phase_bonus += 2.5
            elif action.move_type == MoveType.PRIME:
                phase_bonus += 1.0
        elif phase == "late":
            # Improvement: PRIME is better than PLAIN even in late game if we're not carpeting.
            if action.move_type == MoveType.PRIME:
                phase_bonus += 0.8
            elif action.move_type == MoveType.CARPET:
                phase_bonus += 3.0

        carpet_setup = self._chain_score(board_after, dest, analysis=snap_after)
        carpet_setup += self._prime_direction_bonus(board, action, dest, analysis=snap_before)
        
        # Improvement: Carpet Completion Bonus weighted by length to favor 3+ over 2.
        if action.move_type == MoveType.CARPET:
            if action.roll_length >= 3:
                carpet_setup += immediate * 0.6
            elif action.roll_length == 2:
                carpet_setup += immediate * 0.2

        denial = max(0.0, 8.0 - opponent_moves) / 8.0
        denial += self._high_value_deny_bonus(board, action, dest, analysis=snap_before)
        sabotage_bonus = 0.0
        if self.enable_opponent_chain_sabotage:
            sabotage_bonus = self._opponent_chain_threat_bonus(board, action, dest, analysis=snap_before)
        denial_carpet = self._denial_carpet_bonus(board, action)
        contention_bonus = self._cluster_contention_bonus(board, action, dest, analysis=snap_before)

        risk = self._risk_score(exit_count)
        risk += self._corridor_trap_penalty(board_after, dest, exit_count)

        fragmentation = self._fragmentation_score(
            board,
            board_after,
            action,
            before_analysis=snap_before,
            after_analysis=snap_after,
        )

        turns_left = board.player_worker.turns_left
        timing_adj = self._carpet_timing_adjustment(
            board,
            action,
            turns_left,
            analysis=snap_before,
            deep_eval=deep_eval,
        )
        timing_adj += self._carpet_landing_adjustment(board_after, action, dest)
        if (
            self.enable_threatened_cashout_bonus
            and action.move_type == MoveType.CARPET
            and action.roll_length >= self.threatened_cashout_min_roll
        ):
            opp_loc = board.opponent_worker.get_location()
            cur = board.player_worker.get_location()
            chain_threatened = False
            for _ in range(action.roll_length):
                cur = loc_after_direction(cur, action.direction)
                if abs(cur[0] - opp_loc[0]) + abs(cur[1] - opp_loc[1]) <= self.threatened_cashout_opp_dist:
                    chain_threatened = True
                    break
            if chain_threatened:
                timing_adj += self.threatened_cashout_bonus

        anti_oscillation = 0.0
        if action.move_type == MoveType.PLAIN and state.last_own_move is not None:
            if (
                state.last_own_move.move_type in (MoveType.PLAIN, MoveType.PRIME)
                and action.direction is not None
                and state.last_own_move.direction is not None
                and action.direction == _REVERSE_DIR.get(state.last_own_move.direction)
            ):
                anti_oscillation -= 1.0
            if len(state.recent_positions) >= 2 and dest in (state.recent_positions[-1], state.recent_positions[-2]):
                anti_oscillation -= 0.5

        # --- Solution D: Lookahead-Refined Scoring ---
        # Pillar 2: Adversarial Denial (The "No-Mistakes" Guard).
        # Penalize moves that leave the opponent with high-value gains.
        opp_best_response = self._estimate_opponent_best_response(board_after)

        total = (
            state.effective_a * immediate
            + state.effective_b * position
            + state.effective_c * carpet_setup
            + state.effective_d * denial
            - state.effective_f * risk
            - self.g * fragmentation
            - 0.15 * opp_best_response  # Restored to 0.15 for assertive pacing
            - mobility_penalty         # Counter pinning strategies
            + timing_adj
            + sabotage_bonus
            + anti_oscillation
            + denial_carpet
            + contention_bonus
            + phase_bonus
        )

        continuation = self._continuation_tiebreak(action, state)
        return total, {
            "mobility": float(exit_count),
            "immediate": immediate,
            "risk": risk,
            "continuation": continuation,
        }

    @staticmethod
    def score_search(belief: BeliefEngine, search_move: Move) -> float:
        if search_move.move_type != MoveType.SEARCH or search_move.search_loc is None:
            return float("-inf")
        p = belief.probability_at(search_move.search_loc)
        return 6.0 * p - 2.0

    def _estimate_opponent_best_response(self, board: Board) -> float:
        """Find the maximum immediate point gain an opponent can achieve (Prime/Carpet)."""
        # Note: board is already in our perspective, but we want the opponent's best response,
        # so we look at the 'opponent_worker' and their legal moves.
        # forecast_move would handle the reverse_perspective automatically if we use enemy=True
        # but the engine's get_valid_moves(enemy=True) is faster.
        best_gain = 0.0
        # Iterate over directions to find immediate Prime or Carpet gains.
        opp_loc = board.opponent_worker.get_location()
        for d in (Direction.UP, Direction.DOWN, Direction.LEFT, Direction.RIGHT):
            nxt = loc_after_direction(opp_loc, d)
            if not board.is_valid_cell(nxt):
                continue
            
            # Check Prime
            if not board.is_cell_blocked(nxt):
                # Opponent can potentially Prime (requires being on SPACE)
                # We skip deep validity check for speed, approximating the gain.
                best_gain = max(best_gain, 1.0)
            
            # Check Carpet
            k = self._adjacent_primed_chain_len(board, nxt, d)
            if k >= 2:
                # Need to check if the opponent can actually step onto the entry cell
                # and if they are not already on it.
                if not board.is_cell_blocked(nxt):
                    best_gain = max(best_gain, float(CARPET_POINTS_TABLE[min(k, 7)]))
        
        return best_gain

    def _greed_rollout_m_non(self, board: Board, k: int) -> float:
        if k <= 0:
            return 0.0

        cache_key = (
            board._space_mask,
            board._primed_mask,
            board._carpet_mask,
            board.player_worker.get_location(),
            k,
        )
        cached = self._rollout_cache.get(cache_key)
        if cached is not None:
            return cached

        best = 0.0
        moves = board.get_valid_moves(exclude_search=True)
        if not moves:
            self._rollout_cache[cache_key] = 0.0
            return 0.0
        for m in moves:
            if not board.is_valid_move(m):
                continue
            gain = 0.0
            if m.move_type == MoveType.PRIME:
                gain = 1.0
            elif m.move_type == MoveType.CARPET:
                gain = float(CARPET_POINTS_TABLE[min(m.roll_length, 7)])
            board_after = board.forecast_move(m, check_ok=True)
            if board_after is None:
                continue
            best = max(best, gain + self._greed_rollout_m_non(board_after, k - 1))

        self._rollout_cache[cache_key] = best
        return best

    def _endgame_search_pwin(
        self,
        belief_vec: np.ndarray,
        my_score: float,
        turns_left: int,
        e_opp_final: float,
        m_non_by_k: list[float],
    ) -> float:
        """Win probability of optimal search-vs-non-search mix over remaining endgame turns.

        Uses a small recursive tree (at most 2^turns_left leaves) to evaluate
        multi-turn search sequences where each miss eliminates one cell and
        sharpens the belief for the next attempt.
        """
        if turns_left <= 0:
            return 1.0 if my_score > e_opp_final else 0.0

        pwin_non = 1.0 if my_score + m_non_by_k[turns_left] > e_opp_final else 0.0

        top_idx = int(np.argmax(belief_vec))
        p_top = float(belief_vec[top_idx])
        if p_top <= 0.0:
            return pwin_non

        pwin_hit = 1.0 if my_score + 4.0 + m_non_by_k[turns_left - 1] > e_opp_final else 0.0

        miss_belief = belief_vec.copy()
        miss_belief[top_idx] = 0.0
        s = miss_belief.sum()
        if s > 0:
            miss_belief /= s
        else:
            miss_belief[:] = 1.0 / len(miss_belief)

        pwin_after_miss = self._endgame_search_pwin(
            miss_belief, my_score - 2.0, turns_left - 1, e_opp_final, m_non_by_k,
        )

        pwin_search = p_top * pwin_hit + (1.0 - p_top) * pwin_after_miss
        return max(pwin_search, pwin_non)

    def _observe_opponent_and_maybe_adapt(self, board: Board, state: RuntimeState) -> None:
        snap = state.snapshot_at_our_turn_start
        cat = infer_opponent_category(snap, state.last_own_move, board)
        opp_mob = len(board.get_valid_moves(enemy=True, exclude_search=True))
        state.opp_turn_buffer.append((cat, opp_mob))

        if cat is not None:
            state.observed_turns += 1

        if snap is not None:
            ol, ors = self.parse_search_tuple(snap.opponent_search)
            nl, nrs = self.parse_search_tuple(board.opponent_search)
            if nl is not None and nrs in (True, False) and (nl, nrs) != (ol, ors):
                state.opp_search_attempts += 1
                if nrs:
                    state.opp_search_correct += 1

        state.plies_as_player += 1

        # Coefficient adaptation is applied in select_action after phase scaling (§7.2 ordering).

    def _best_safe_non_search(self, board: Board) -> Move:
        moves = board.get_valid_moves(exclude_search=True)
        plain_moves = [m for m in moves if m.move_type == MoveType.PLAIN]
        if plain_moves:
            plain_moves.sort(key=self.move_sort_key)
            return plain_moves[0]
        if moves:
            moves.sort(key=self.move_sort_key)
            return moves[0]
        # In case entirely trapped (should rarely happen)
        return board.get_valid_moves(exclude_search=False)[0]

    def _late_phase_filter_non_search(
        self,
        board: Board,
        moves: list[Move],
        *,
        analysis: BoardAnalysis | None = None,
    ) -> list[Move]:
        """Late-phase priority filter (§1.3): cash out carpets first, then tactical setup."""
        if not moves:
            return moves
        snap = analysis or self._analysis_for(board)

        carpets_ge3 = [m for m in moves if m.move_type == MoveType.CARPET and m.roll_length >= 3]
        if carpets_ge3:
            return carpets_ge3

        carpets_2 = [m for m in moves if m.move_type == MoveType.CARPET and m.roll_length == 2]
        if carpets_2:
            return carpets_2

        turns_left = board.player_worker.turns_left
        if turns_left >= 2:
            prime_setup = [
                m
                for m in moves
                if m.move_type == MoveType.PRIME and self._prime_enables_next_turn_carpet(board, m, min_roll=3)
            ]
            if prime_setup:
                return prime_setup
            
            # IMPROVEMENT: Even if no immediate carpet setup, still allow PRIME moves
            # to capture the +1 point and prepare future options.
            all_primes = [m for m in moves if m.move_type == MoveType.PRIME]
            if all_primes:
                return all_primes
        elif turns_left <= 2:
            late_primes = [m for m in moves if m.move_type == MoveType.PRIME]
            if late_primes:
                return late_primes

        plains = [m for m in moves if m.move_type == MoveType.PLAIN]
        if plains:
            if snap.entry_map:
                src = board.player_worker.get_location()
                src_d = snap.dist_to_nearest_entry(src)
                closer: list[Move] = []
                for m in plains:
                    d = snap.dist_to_nearest_entry(self._destination(board, m))
                    if d is not None and (src_d is None or d < src_d):
                        closer.append(m)
                if closer:
                    return closer
            return plains
        return moves

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
        self._rollout_cache.clear()

        if state.enable_opponent_model:
            self._observe_opponent_and_maybe_adapt(board, state)

        def _persist_return(mv: Move) -> Move:
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
            state.last_own_move = mv
            state.fallback_move = mv
            state.fallback_turn = board.turn_count
            state.recent_positions.append(board.player_worker.get_location())
            return mv

        if self.enable_fast_search_shortcut:
            # Fast-search shortcut: only fire when belief is highly concentrated and no strong carpet exists.
            best_immediate_carpet = 0.0
            for mv in board.get_valid_moves(exclude_search=True):
                if mv.move_type != MoveType.CARPET:
                    continue
                best_immediate_carpet = max(best_immediate_carpet, float(CARPET_POINTS_TABLE[min(mv.roll_length, 7)]))
            top_k = belief.topk(1)
            if top_k and best_immediate_carpet < self.fast_search_max_carpet_points:
                top_loc, top_prob = top_k[0]
                if top_prob > self.fast_search_prob_threshold:
                    smove = Move.search(top_loc)
                    if board.is_valid_move(smove):
                        return _persist_return(smove)

        candidates = self.generate_candidates(board, belief)
        if not candidates or emergency or now <= state.emergency_floor_total:
            return _persist_return(self._best_safe_non_search(board))
        deep_eval_enabled, deep_top_k = TimeManager.deep_path_plan(board, state, now, alloc)

        snap_root = BoardAnalysis(board)
        self._active_root_board = board
        self._active_root_analysis = snap_root
        self._opp_carpet_threat_cells, self._opp_carpet_threat_value = self._compute_opp_carpet_threats(board)

        my_turns = board.player_worker.turns_left
        my_score = board.player_worker.get_points()

        # --- Phase-dependent coefficient modulation (§7.2) ---
        phase = self._get_phase(my_turns)
        ma, mb, mc, md, mf = self._phase_multipliers(phase)
        phase_a = self.a * ma
        phase_b = self.b * mb
        phase_c = self.c * mc
        phase_d = self.d * md
        phase_f = self.f * mf

        # Apply adaptation after phase scaling (required ordering in §7.2).
        if state.enable_opponent_model:
            phase_a, phase_c, phase_d, phase_f = self._adapted_coefficients(
                state, phase_a, phase_c, phase_d, phase_f
            )

        state.effective_a = phase_a
        state.effective_b = phase_b
        state.effective_c = phase_c
        state.effective_d = phase_d
        state.effective_f = phase_f

        # --- Score-pressure modulation (§8.3–8.4) ---
        self._apply_score_pressure(board, state)

        search_candidates = [m for m in candidates if m.move_type == MoveType.SEARCH]
        non_search_candidates = [m for m in candidates if m.move_type != MoveType.SEARCH]

        if phase == "late":
            non_search_candidates = self._late_phase_filter_non_search(
                board,
                non_search_candidates,
                analysis=snap_root,
            )

        # --- Last-turn hard constraint (§1.3, §13): no plain step if point action exists ---
        if my_turns <= 1:
            point_moves = [m for m in non_search_candidates if m.move_type != MoveType.PLAIN]
            if point_moves:
                non_search_candidates = point_moves

        # Corridor traps are vetoed unless every remaining non-search move is a corridor trap.
        corridor_flags: dict[tuple, bool] = {}
        single_exit_flags: dict[tuple, bool] = {}
        board_after_cache: dict[tuple, Board | None] = {}
        non_corridor_exists = False
        multi_exit_exists = False
        for mv in non_search_candidates:
            key = (mv.move_type, mv.direction, mv.roll_length, mv.search_loc)
            bd_after = board.forecast_move(mv, check_ok=True)
            board_after_cache[key] = bd_after
            if bd_after is None:
                corridor_flags[key] = False
                single_exit_flags[key] = False
                non_corridor_exists = True
                continue
            dest = self._destination(board, mv)
            exits = self._count_plain_exits(bd_after, dest)
            single_exit = exits == 1
            single_exit_flags[key] = single_exit
            if exits >= 2:
                multi_exit_exists = True

            flag = False
            if single_exit:
                single_out = self._single_plain_exit(bd_after, dest)
                if single_out is not None:
                    exits_of_exit = self._count_plain_exits(bd_after, single_out, exclude={dest})
                    flag = exits_of_exit <= 1
            corridor_flags[key] = flag
            if not flag:
                non_corridor_exists = True

        best_non_search: Move | None = None
        best_non_search_tv = float("-inf")
        best_non_search_meta = {"mobility": 0.0, "immediate": 0.0, "risk": 0.0, "continuation": 0.0}
        best_non_search_heuristic_tv = float("-inf")

        best_search: Move | None = None
        best_search_sv = float("-inf")

        for mv in sorted(search_candidates, key=self.move_sort_key):
            if time.perf_counter() >= turn_deadline:
                break

            sv = self.score_search(belief, mv)
            if sv > best_search_sv or (
                sv == best_search_sv
                and best_search is not None
                and self.move_sort_key(mv) < self.move_sort_key(best_search)
            ):
                best_search = mv
                best_search_sv = sv

        filtered_non_search_candidates: list[Move] = []
        for mv in sorted(non_search_candidates, key=self.move_sort_key):
            # Do not filter PLAIN moves into corridors! The deep search will evaluate safety.
            filtered_non_search_candidates.append(mv)
        if not filtered_non_search_candidates:
            filtered_non_search_candidates = sorted(non_search_candidates, key=self.move_sort_key)

        def _rank_non_search_heuristic(pool: list[Move]) -> tuple[Move | None, float, dict[str, float]]:
            best_mv: Move | None = None
            best_tv = float("-inf")
            best_meta = {"mobility": 0.0, "immediate": 0.0, "risk": 0.0, "continuation": 0.0}
            deep_keys: set[tuple] = set()

            if deep_eval_enabled and deep_top_k > 0 and pool:
                coarse_rank: list[tuple[float, tuple]] = []
                for mv in pool:
                    mv_key = (mv.move_type, mv.direction, mv.roll_length, mv.search_loc)
                    if mv.move_type == MoveType.CARPET:
                        coarse = float(CARPET_POINTS_TABLE[min(mv.roll_length, 7)]) + self._denial_carpet_bonus(board, mv)
                    elif mv.move_type == MoveType.PRIME:
                        coarse = 1.0 + 0.2 * self._prime_future_potential(board, mv)
                    else:
                        coarse = 0.0
                    coarse_rank.append((coarse, mv_key))
                coarse_rank.sort(key=lambda x: -x[0])
                deep_keys = {mv_key for _, mv_key in coarse_rank[:deep_top_k]}

            for mv in pool:
                if time.perf_counter() >= turn_deadline:
                    break
                mv_key = (mv.move_type, mv.direction, mv.roll_length, mv.search_loc)
                cached_ba = board_after_cache.get(mv_key)
                tv, meta = self.score_non_search(
                    board, mv, belief, state,
                    precomputed_board_after=cached_ba,
                    deep_eval=(mv_key in deep_keys),
                )
                if tv > best_tv or (
                    tv == best_tv
                    and (
                        meta["mobility"],
                        meta["immediate"],
                        -meta["risk"],
                        meta["continuation"],
                        tuple(self.move_sort_key(mv)),
                    )
                    > (
                        best_meta["mobility"],
                        best_meta["immediate"],
                        -best_meta["risk"],
                        best_meta["continuation"],
                        tuple(self.move_sort_key(best_mv)) if best_mv else (999, 999, 999),
                    )
                ):
                    best_mv = mv
                    best_tv = tv
                    best_meta = meta
            return best_mv, best_tv, best_meta

        if my_turns > 3 and filtered_non_search_candidates:
            lookahead_budget = max(0.0, (turn_deadline - time.perf_counter()) * 0.75)
            searcher = Lookahead(self, snap_root)
            tree_move, tree_value, completed_depth2 = searcher.rank_moves(
                board,
                filtered_non_search_candidates,
                lookahead_budget,
                belief_vec=belief.belief,
            )
            if completed_depth2 and tree_move is not None:
                best_non_search = tree_move
                best_non_search_tv = tree_value
                tm_key = (tree_move.move_type, tree_move.direction, tree_move.roll_length, tree_move.search_loc)
                best_non_search_heuristic_tv, best_non_search_meta = self.score_non_search(
                    board,
                    tree_move,
                    belief,
                    state,
                    precomputed_board_after=board_after_cache.get(tm_key),
                    deep_eval=deep_eval_enabled,
                )
                if tree_move.move_type != MoveType.CARPET:
                    h_mv, h_tv, h_meta = _rank_non_search_heuristic(filtered_non_search_candidates)
                    if (
                        h_mv is not None
                        and h_mv.move_type == MoveType.CARPET
                        and h_mv.roll_length >= 3
                        and h_tv > best_non_search_heuristic_tv
                    ):
                        best_non_search = h_mv
                        best_non_search_tv = h_tv
                        best_non_search_meta = h_meta
                        best_non_search_heuristic_tv = h_tv
            else:
                best_non_search, best_non_search_tv, best_non_search_meta = _rank_non_search_heuristic(
                    filtered_non_search_candidates
                )
                best_non_search_heuristic_tv = best_non_search_tv
        else:
            best_non_search, best_non_search_tv, best_non_search_meta = _rank_non_search_heuristic(
                filtered_non_search_candidates
            )
            best_non_search_heuristic_tv = best_non_search_tv

        if best_search is None:
            return _persist_return(best_non_search if best_non_search else self._best_safe_non_search(board))

        # §8.1 "No good move" ordering.
        if best_non_search is None or best_non_search_heuristic_tv <= 0.0:
            if best_search_sv > 0.0:
                return _persist_return(best_search)
            fallback_pool = filtered_non_search_candidates if filtered_non_search_candidates else non_search_candidates
            return _persist_return(self._no_good_move_fallback(board, fallback_pool, analysis=snap_root))

        p1 = belief.probability_at(best_search.search_loc) if best_search.search_loc else 0.0

        if my_turns > 3:
            # Standard Mode (§9.1): Balanced search vs movement.
            # Use stable logic exactly as in Yolanda3_2 to match search aggression baseline (§10.2).
            q_best_non = 0.0
            if best_non_search.move_type == MoveType.PRIME:
                q_best_non = 1.0
                bn_key = (best_non_search.move_type, best_non_search.direction, best_non_search.roll_length, best_non_search.search_loc)
                bn_ba = board_after_cache.get(bn_key)
                if bn_ba is not None:
                    # Look ahead 1-ply for carpet conversion potential.
                    for mv in bn_ba.get_valid_moves(exclude_search=True):
                        if mv.move_type == MoveType.CARPET and mv.roll_length >= 3:
                            carpet_pts = float(CARPET_POINTS_TABLE[min(mv.roll_length, 7)])
                            # Match precise 3.2 logic: cap at 2.0 bonus.
                            q_best_non = max(q_best_non, 1.0 + min(2.0, 0.15 * carpet_pts))
            elif best_non_search.move_type == MoveType.CARPET:
                q_best_non = float(CARPET_POINTS_TABLE[min(best_non_search.roll_length, 7)])
            
            # Dynamic Margin (§9.2) matching 3.2 baseline + 0.1 adjustment for selectivity
            turn_fraction = my_turns / 40.0
            
            # Pillar 4: Lead-Aware Stability (Margin of Safety).
            # Situational Awareness: Lead-aware margin adjustment
            opp_score = board.opponent_worker.get_points()
            score_delta = my_score - opp_score
            
            # If we have a solid lead, be more conservative with rat guesses.
            # If we are significantly behind, we may need to be slightly more aggressive.
            lead_adjustment = 0.0
            if score_delta > 3:
                # Solid lead: be more conservative to avoid unnecessary penalties.
                lead_adjustment = 0.15 + 0.03 * score_delta
            elif score_delta < -8:
                # Behind: slightly more aggressive to catch up.
                lead_adjustment = -0.15 + 0.01 * score_delta
            
            lead_adjustment = max(-0.5, min(0.8, lead_adjustment))
            
            if state.farmable_rat:
                q_best_non *= 0.90
                guess_margin = 0.15 + 0.20 * turn_fraction + lead_adjustment
            else:
                guess_margin = 0.25 + 0.50 * turn_fraction + lead_adjustment
                
            if 6.0 * p1 - 2.0 >= (q_best_non + guess_margin):
                return _persist_return(best_search)
            return _persist_return(best_non_search if best_non_search else self._best_safe_non_search(board))
        else:
            # Endgame Mode
            opp_points = board.opponent_worker.get_points()
            opp_turns = board.opponent_worker.turns_left

            opp_board = board.get_copy()
            opp_board.reverse_perspective()
            e_opp_final = opp_points + self._greed_rollout_m_non(opp_board, opp_turns)

            m_non_by_k = [self._greed_rollout_m_non(board, k) for k in range(my_turns + 1)]

            # Multi-turn search tree: accounts for belief sharpening after
            # successive misses and compares cumulative catch probability
            # against the non-search path at every level.
            pwin_search = self._endgame_search_pwin(
                belief.belief.copy(), my_score, my_turns, e_opp_final, m_non_by_k,
            )

            best_action = best_search if pwin_search > 0.0 else None
            best_pwin = pwin_search

            for mv in non_search_candidates:
                if time.perf_counter() >= turn_deadline:
                    break
                bd_after = board.forecast_move(mv, check_ok=True)
                if not bd_after:
                    continue
                gain = 1.0 if mv.move_type == MoveType.PRIME else (float(CARPET_POINTS_TABLE[min(mv.roll_length, 7)]) if mv.move_type == MoveType.CARPET else 0.0)
                m_non = self._greed_rollout_m_non(bd_after, my_turns - 1)
                pwin_a = 1.0 if my_score + gain + m_non > e_opp_final else 0.0
                if pwin_a > best_pwin or (pwin_a == best_pwin and mv == best_non_search):
                    best_pwin = pwin_a
                    best_action = mv

            return _persist_return(best_action if best_action else self._best_safe_non_search(board))
