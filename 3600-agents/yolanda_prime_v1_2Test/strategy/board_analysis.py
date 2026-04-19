from __future__ import annotations

from collections.abc import Iterable

from game.board import Board
from game.enums import BOARD_SIZE, CARPET_POINTS_TABLE, Direction, loc_after_direction


BOARD_CELLS = BOARD_SIZE * BOARD_SIZE
INF = 255
_DIRECTIONS: tuple[Direction, Direction, Direction, Direction] = (
    Direction.UP,
    Direction.DOWN,
    Direction.LEFT,
    Direction.RIGHT,
)


def _points_for_chain_len(length: int) -> float:
    if length <= 1:
        return 0.0
    return float(CARPET_POINTS_TABLE[min(length, 7)])


def _loc_to_index(loc: tuple[int, int]) -> int:
    return loc[1] * BOARD_SIZE + loc[0]


def _index_to_loc(index: int) -> tuple[int, int]:
    return (index % BOARD_SIZE, index // BOARD_SIZE)


_NEIGHBORS_BY_INDEX: tuple[tuple[int, ...], ...] = tuple(
    tuple(
        nidx
        for nidx in (
            ((idx // BOARD_SIZE - 1) * BOARD_SIZE + (idx % BOARD_SIZE)) if idx // BOARD_SIZE > 0 else -1,
            ((idx // BOARD_SIZE + 1) * BOARD_SIZE + (idx % BOARD_SIZE)) if idx // BOARD_SIZE < BOARD_SIZE - 1 else -1,
            ((idx // BOARD_SIZE) * BOARD_SIZE + (idx % BOARD_SIZE - 1)) if idx % BOARD_SIZE > 0 else -1,
            ((idx // BOARD_SIZE) * BOARD_SIZE + (idx % BOARD_SIZE + 1)) if idx % BOARD_SIZE < BOARD_SIZE - 1 else -1,
        )
        if nidx >= 0
    )
    for idx in range(BOARD_CELLS)
)


class BoardAnalysis:
    """Per-turn board snapshot with O(1) pathing and chain-access queries."""

    def __init__(self, board: Board) -> None:
        self.board = board

        self.player_idx = _loc_to_index(board.player_worker.get_location())
        self.opponent_idx = _loc_to_index(board.opponent_worker.get_location())

        self.walkable_mask = [False] * BOARD_CELLS
        self.walkable_mask_include_occupied = [False] * BOARD_CELLS
        self._build_walkable_masks()

        # Dense 64x64 matrix flattened row-major; INF marks unreachable pairs.
        self._dist_matrix = [INF] * (BOARD_CELLS * BOARD_CELLS)
        self._build_distance_matrix()

        self._entry_best_len, self._entry_best_dir = self._build_entry_data(include_occupied=False)
        self._entry_best_len_inc, self._entry_best_dir_inc = self._build_entry_data(include_occupied=True)
        self.entry_map = {
            idx: (self._entry_best_len[idx], self._entry_best_dir[idx])
            for idx in range(BOARD_CELLS)
            if self._entry_best_len[idx] >= 3 and self._entry_best_dir[idx] is not None
        }
        self._chain_profile = self._build_chain_profiles(include_occupied=False)
        self._chain_profile_inc = self._build_chain_profiles(include_occupied=True)

        self.space_components = self._count_space_components()

        self.primable_corridor_mask = self._build_primable_corridor_mask()
        self._primed_cluster_profiles = self._build_primed_cluster_profiles()

        self._dist_to_nearest_entry_raw = self._multi_source_walkable_distance(self.entry_map.keys())
        primable_seeds = [idx for idx in range(BOARD_CELLS) if self.primable_corridor_mask[idx] and self.walkable_mask[idx]]
        self._dist_to_nearest_primable_raw = self._multi_source_walkable_distance(primable_seeds)
        self._reachable_best_chain_value_raw = self._build_reachable_best_chain_values()

    @staticmethod
    def index_from_loc(loc: tuple[int, int]) -> int:
        return _loc_to_index(loc)

    @staticmethod
    def loc_from_index(index: int) -> tuple[int, int]:
        return _index_to_loc(index)

    def _to_index(self, cell: tuple[int, int] | int) -> int:
        if isinstance(cell, int):
            return cell
        return _loc_to_index(cell)

    def entry_map_for(
        self,
        min_chain_len: int = 3,
        *,
        include_occupied: bool = False,
    ) -> dict[int, tuple[int, Direction]]:
        best_len = self._entry_best_len_inc if include_occupied else self._entry_best_len
        best_dir = self._entry_best_dir_inc if include_occupied else self._entry_best_dir
        result: dict[int, tuple[int, Direction]] = {}
        for idx in range(BOARD_CELLS):
            d = best_dir[idx]
            k = best_len[idx]
            if d is None or k < min_chain_len:
                continue
            result[idx] = (k, d)
        return result

    def dist(self, a: tuple[int, int] | int, b: tuple[int, int] | int) -> int:
        ia = self._to_index(a)
        ib = self._to_index(b)
        if ia == ib:
            return 0

        starts = self._endpoint_candidates(ia)
        ends = self._endpoint_candidates(ib)
        if not starts or not ends:
            return INF

        best = INF
        for s_idx, s_cost in starts:
            row = s_idx * BOARD_CELLS
            for e_idx, e_cost in ends:
                d = self._dist_matrix[row + e_idx]
                if d >= INF:
                    continue
                total = s_cost + d + e_cost
                if total < best:
                    best = total
        return best

    def dist_to_nearest_entry(self, cell: tuple[int, int] | int) -> int | None:
        idx = self._to_index(cell)
        return self._distance_from_walkable_map(idx, self._dist_to_nearest_entry_raw)

    def dist_to_nearest_primable(self, cell: tuple[int, int] | int) -> int | None:
        idx = self._to_index(cell)
        if self.primable_corridor_mask[idx]:
            return 0
        return self._distance_from_walkable_map(idx, self._dist_to_nearest_primable_raw)

    def reachable_best_chain_value(self, cell: tuple[int, int] | int) -> float:
        idx = self._to_index(cell)
        if self.walkable_mask[idx]:
            return self._reachable_best_chain_value_raw[idx]

        best = 0.0
        for nxt in _NEIGHBORS_BY_INDEX[idx]:
            if not self.walkable_mask[nxt]:
                continue
            best = max(best, self._reachable_best_chain_value_raw[nxt])
        return best

    def chain_profile(
        self,
        entry: tuple[int, int] | int,
        direction: Direction,
        *,
        include_occupied: bool = False,
    ) -> dict[str, float]:
        idx = self._to_index(entry)
        source = self._chain_profile_inc if include_occupied else self._chain_profile
        # NOTE: Profiles are cached once per board snapshot so policy code can query
        # composite chain opportunities without rescanning rays every action.
        return source.get(
            (idx, direction),
            {
                "straight_len": 0.0,
                "perp_extension": 0.0,
                "immediate_value": 0.0,
                "composite_value": 0.0,
                "defer_value": 0.0,
            },
        )

    def best_chain_profile(self, entry: tuple[int, int] | int, *, include_occupied: bool = False) -> dict[str, float]:
        idx = self._to_index(entry)
        best = {
            "straight_len": 0.0,
            "perp_extension": 0.0,
            "immediate_value": 0.0,
            "composite_value": 0.0,
            "defer_value": 0.0,
        }
        source = self._chain_profile_inc if include_occupied else self._chain_profile
        for direction in _DIRECTIONS:
            prof = source.get((idx, direction))
            if prof is None:
                continue
            if prof["composite_value"] > best["composite_value"] or (
                prof["composite_value"] == best["composite_value"] and prof["defer_value"] > best["defer_value"]
            ):
                best = prof
        return best

    def primed_cluster_profiles(self) -> tuple[dict[str, object], ...]:
        return self._primed_cluster_profiles

    def _build_walkable_masks(self) -> None:
        worker_indices = {self.player_idx, self.opponent_idx}
        for idx in range(BOARD_CELLS):
            loc = _index_to_loc(idx)
            cell_name = self.board.get_cell(loc).name
            is_walkable_type = cell_name in {"SPACE", "CARPET"}
            self.walkable_mask_include_occupied[idx] = is_walkable_type
            self.walkable_mask[idx] = is_walkable_type and idx not in worker_indices

    def _build_distance_matrix(self) -> None:
        for src in range(BOARD_CELLS):
            base = src * BOARD_CELLS
            self._dist_matrix[base + src] = 0
            if not self.walkable_mask[src]:
                continue

            visited = [False] * BOARD_CELLS
            visited[src] = True
            queue: list[int] = [src]
            qidx = 0
            while qidx < len(queue):
                cur = queue[qidx]
                qidx += 1
                nd = self._dist_matrix[base + cur] + 1
                for nxt in _NEIGHBORS_BY_INDEX[cur]:
                    if visited[nxt] or not self.walkable_mask[nxt]:
                        continue
                    visited[nxt] = True
                    self._dist_matrix[base + nxt] = nd
                    queue.append(nxt)

    def _adjacent_primed_chain_len(self, entry: tuple[int, int], direction: Direction) -> int:
        cur = entry
        length = 0
        for _ in range(BOARD_SIZE - 1):
            cur = loc_after_direction(cur, direction)
            if not self.board.is_valid_cell(cur):
                break
            if self.board.get_cell(cur).name != "PRIMED":
                break
            length += 1
        return length

    def _build_entry_data(self, *, include_occupied: bool) -> tuple[list[int], list[Direction | None]]:
        mask = self.walkable_mask_include_occupied if include_occupied else self.walkable_mask
        best_len = [0] * BOARD_CELLS
        best_dir: list[Direction | None] = [None] * BOARD_CELLS

        for idx in range(BOARD_CELLS):
            if not mask[idx]:
                continue
            loc = _index_to_loc(idx)
            k_best = 0
            d_best: Direction | None = None
            for direction in _DIRECTIONS:
                k = self._adjacent_primed_chain_len(loc, direction)
                if k > k_best:
                    k_best = k
                    d_best = direction
            best_len[idx] = k_best
            best_dir[idx] = d_best

        return best_len, best_dir

    @staticmethod
    def _perpendicular_dirs(direction: Direction) -> tuple[Direction, Direction]:
        if direction in (Direction.UP, Direction.DOWN):
            return Direction.LEFT, Direction.RIGHT
        return Direction.UP, Direction.DOWN

    def _count_contiguous_primed(self, start: tuple[int, int], direction: Direction) -> int:
        cur = start
        count = 0
        for _ in range(BOARD_SIZE - 1):
            cur = loc_after_direction(cur, direction)
            if not self.board.is_valid_cell(cur):
                break
            if self.board.get_cell(cur).name != "PRIMED":
                break
            count += 1
        return count

    def _build_chain_profiles(self, *, include_occupied: bool) -> dict[tuple[int, Direction], dict[str, float]]:
        mask = self.walkable_mask_include_occupied if include_occupied else self.walkable_mask
        profiles: dict[tuple[int, Direction], dict[str, float]] = {}
        for idx in range(BOARD_CELLS):
            if not mask[idx]:
                continue
            entry = _index_to_loc(idx)
            for direction in _DIRECTIONS:
                straight_len = self._adjacent_primed_chain_len(entry, direction)
                if straight_len <= 0:
                    continue
                perp_a, perp_b = self._perpendicular_dirs(direction)
                perp_extension = 0
                cur = entry
                for _ in range(straight_len):
                    cur = loc_after_direction(cur, direction)
                    side_a = self._count_contiguous_primed(cur, perp_a)
                    side_b = self._count_contiguous_primed(cur, perp_b)
                    perp_extension = max(perp_extension, side_a, side_b, side_a + side_b)

                immediate = _points_for_chain_len(straight_len)
                composite = _points_for_chain_len(max(straight_len, perp_extension))
                extension_delta = max(0.0, _points_for_chain_len(straight_len + 1) - immediate)
                branch_delta = max(0.0, composite - immediate)
                defer_value = immediate + max(extension_delta, 0.7 * branch_delta)

                profiles[(idx, direction)] = {
                    "straight_len": float(straight_len),
                    "perp_extension": float(perp_extension),
                    "immediate_value": immediate,
                    "composite_value": composite,
                    "defer_value": defer_value,
                }
        return profiles

    def _count_space_components(self) -> int:
        worker_indices = {self.player_idx, self.opponent_idx}
        visited = [False] * BOARD_CELLS
        components = 0

        for idx in range(BOARD_CELLS):
            if visited[idx] or idx in worker_indices:
                continue
            if self.board.get_cell(_index_to_loc(idx)).name != "SPACE":
                continue

            components += 1
            visited[idx] = True
            stack = [idx]
            while stack:
                cur = stack.pop()
                for nxt in _NEIGHBORS_BY_INDEX[cur]:
                    if visited[nxt] or nxt in worker_indices:
                        continue
                    if self.board.get_cell(_index_to_loc(nxt)).name != "SPACE":
                        continue
                    visited[nxt] = True
                    stack.append(nxt)

        return components

    def _build_primable_corridor_mask(self) -> list[bool]:
        mask = [False] * BOARD_CELLS

        for idx in range(BOARD_CELLS):
            if not self.walkable_mask_include_occupied[idx]:
                continue
            loc = _index_to_loc(idx)
            if self.board.get_cell(loc).name != "SPACE":
                continue

            for nxt in _NEIGHBORS_BY_INDEX[idx]:
                if nxt == self.opponent_idx:
                    continue
                if self.board.get_cell(_index_to_loc(nxt)).name == "SPACE":
                    mask[idx] = True
                    break

        return mask

    def _multi_source_walkable_distance(self, seeds: Iterable[int]) -> list[int]:
        dist = [INF] * BOARD_CELLS
        queue: list[int] = []

        for seed in seeds:
            if seed < 0 or seed >= BOARD_CELLS:
                continue
            if not self.walkable_mask[seed]:
                continue
            if dist[seed] == 0:
                continue
            dist[seed] = 0
            queue.append(seed)

        qidx = 0
        while qidx < len(queue):
            cur = queue[qidx]
            qidx += 1
            nd = dist[cur] + 1
            for nxt in _NEIGHBORS_BY_INDEX[cur]:
                if not self.walkable_mask[nxt]:
                    continue
                if nd >= dist[nxt]:
                    continue
                dist[nxt] = nd
                queue.append(nxt)

        return dist

    def _distance_from_walkable_map(self, idx: int, dist_map: list[int]) -> int | None:
        if dist_map[idx] < INF:
            return dist_map[idx]

        best = INF
        for nxt in _NEIGHBORS_BY_INDEX[idx]:
            if not self.walkable_mask[nxt]:
                continue
            d = dist_map[nxt]
            if d >= INF:
                continue
            best = min(best, d + 1)

        if best >= INF:
            return None
        return best

    def _build_reachable_best_chain_values(self) -> list[float]:
        component_id = [-1] * BOARD_CELLS
        component_best: list[float] = []

        for idx in range(BOARD_CELLS):
            if not self.walkable_mask[idx] or component_id[idx] != -1:
                continue

            cid = len(component_best)
            queue = [idx]
            component_id[idx] = cid
            qidx = 0
            nodes: list[int] = []
            best = 0.0

            while qidx < len(queue):
                cur = queue[qidx]
                qidx += 1
                nodes.append(cur)

                k = self._entry_best_len[cur]
                if k >= 3:
                    best = max(best, float(CARPET_POINTS_TABLE[min(k, 7)]))

                for nxt in _NEIGHBORS_BY_INDEX[cur]:
                    if not self.walkable_mask[nxt] or component_id[nxt] != -1:
                        continue
                    component_id[nxt] = cid
                    queue.append(nxt)

            component_best.append(best)
            for node in nodes:
                component_id[node] = cid

        values = [0.0] * BOARD_CELLS
        for idx in range(BOARD_CELLS):
            cid = component_id[idx]
            if cid != -1:
                values[idx] = component_best[cid]

        return values

    def _build_primed_cluster_profiles(self) -> tuple[dict[str, object], ...]:
        visited = [False] * BOARD_CELLS
        profiles: list[dict[str, object]] = []

        for idx in range(BOARD_CELLS):
            if visited[idx]:
                continue
            if self.board.get_cell(_index_to_loc(idx)).name != "PRIMED":
                continue

            queue = [idx]
            visited[idx] = True
            qidx = 0
            cells: list[int] = []
            entry_indices: set[int] = set()
            max_run = 0

            while qidx < len(queue):
                cur = queue[qidx]
                qidx += 1
                cells.append(cur)
                cur_loc = _index_to_loc(cur)
                for direction in _DIRECTIONS:
                    run = 1 + self._count_contiguous_primed(cur_loc, direction)
                    max_run = max(max_run, run)

                for nxt in _NEIGHBORS_BY_INDEX[cur]:
                    nxt_loc = _index_to_loc(nxt)
                    if self.board.get_cell(nxt_loc).name == "PRIMED":
                        if not visited[nxt]:
                            visited[nxt] = True
                            queue.append(nxt)
                        continue
                    if self.walkable_mask_include_occupied[nxt]:
                        entry_indices.add(nxt)

            cluster_value = _points_for_chain_len(max_run)
            our_access = min((self.dist(self.player_idx, e_idx) for e_idx in entry_indices), default=INF)
            opp_access = min((self.dist(self.opponent_idx, e_idx) for e_idx in entry_indices), default=INF)

            our_acc = 99.0 if our_access >= INF else float(our_access)
            opp_acc = 99.0 if opp_access >= INF else float(opp_access)
            best_access = min(our_acc, opp_acc)
            disruption_leverage = max(0.0, cluster_value - 0.5 * best_access)

            profiles.append(
                {
                    "cells": tuple(cells),
                    "entries": tuple(sorted(entry_indices)),
                    "cluster_value": cluster_value,
                    "our_access": our_acc,
                    "opp_access": opp_acc,
                    "threat_gap": our_acc - opp_acc,
                    "disruption_leverage": disruption_leverage,
                }
            )

        return tuple(profiles)

    def _endpoint_candidates(self, idx: int) -> list[tuple[int, int]]:
        if self.walkable_mask[idx]:
            return [(idx, 0)]
        return [(nxt, 1) for nxt in _NEIGHBORS_BY_INDEX[idx] if self.walkable_mask[nxt]]
