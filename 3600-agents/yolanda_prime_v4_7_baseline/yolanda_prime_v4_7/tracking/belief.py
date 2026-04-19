from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from game.board import Board
from game.enums import BOARD_SIZE, Cell, Noise
from game.rat import DISTANCE_ERROR_OFFSETS, DISTANCE_ERROR_PROBS, NOISE_PROBS

_N = BOARD_SIZE * BOARD_SIZE
_ALL_LOCS: list[tuple[int, int]] = [(i % BOARD_SIZE, i // BOARD_SIZE) for i in range(_N)]
_CELL_X = np.array([loc[0] for loc in _ALL_LOCS], dtype=np.int32)
_CELL_Y = np.array([loc[1] for loc in _ALL_LOCS], dtype=np.int32)
_LOG_N = float(np.log(_N))


def _idx_to_loc(idx: int) -> tuple[int, int]:
    return _ALL_LOCS[idx]


def _loc_to_idx(loc: tuple[int, int]) -> int:
    return loc[1] * BOARD_SIZE + loc[0]


@dataclass
class BeliefEngine:
    """Tracks rat posterior over all 64 cells (ported from v2 with entropy helper)."""

    transition_matrix: np.ndarray

    def __post_init__(self) -> None:
        t = np.asarray(self.transition_matrix, dtype=np.float64)
        if t.shape != (_N, _N):
            raise ValueError(f"Expected 64x64 transition matrix, got {t.shape}")
        row_sum = t.sum(axis=1, keepdims=True)
        row_sum[row_sum == 0.0] = 1.0
        self.transition_matrix = t / row_sum
        self.transition_matrix_2 = self.transition_matrix @ self.transition_matrix

        start = np.zeros(_N, dtype=np.float64)
        start[0] = 1.0
        self.reset_prior = start @ np.linalg.matrix_power(self.transition_matrix, 1000)
        self.belief = self.reset_prior.copy()

        max_dist = 2 * (BOARD_SIZE - 1)
        max_reported = max_dist + max(DISTANCE_ERROR_OFFSETS)
        self._dist_lut = np.zeros((max_dist + 1, max_reported + 1), dtype=np.float64)
        for d in range(max_dist + 1):
            for offset, prob in zip(DISTANCE_ERROR_OFFSETS, DISTANCE_ERROR_PROBS):
                r = max(0, d + offset)
                if r <= max_reported:
                    self._dist_lut[d, r] += prob

        num_cell_types = max(int(c) for c in Cell) + 1
        self._noise_lut = np.zeros((num_cell_types, 3), dtype=np.float64)
        for cell_type, probs in NOISE_PROBS.items():
            for ni in range(3):
                self._noise_lut[int(cell_type), ni] = probs[ni]

    def _normalize(self, vec: np.ndarray) -> np.ndarray:
        s = float(np.sum(vec))
        if s <= 0:
            return np.full_like(vec, 1.0 / len(vec), dtype=np.float64)
        return vec / s

    def predict(self, use_single_step: bool, opp_miss_cell: tuple[int, int] | None) -> np.ndarray:
        if use_single_step:
            self.belief = self._normalize(self.belief @ self.transition_matrix)
        elif opp_miss_cell is not None:
            b_inter = self._normalize(self.belief @ self.transition_matrix)
            b_inter[_loc_to_idx(opp_miss_cell)] = 0.0
            b_inter = self._normalize(b_inter)
            self.belief = self._normalize(b_inter @ self.transition_matrix)
        else:
            self.belief = self._normalize(self.belief @ self.transition_matrix_2)
        return self.belief

    def update(self, noise: Noise, estimated_distance: int, board: Board) -> np.ndarray:
        wx, wy = board.player_worker.get_location()
        reported = int(estimated_distance)
        noise_idx = int(noise)

        cell_types = np.array(
            [int(board.get_cell(loc)) for loc in _ALL_LOCS], dtype=np.int32
        )
        noise_probs = self._noise_lut[cell_types, noise_idx]
        actual_dists = np.abs(_CELL_X - wx) + np.abs(_CELL_Y - wy)
        
        # Clamp reported distance to the LUT range to avoid IndexErrors from outliers
        max_r = self._dist_lut.shape[1] - 1
        r_clamped = min(max_r, max(0, reported))
        dist_probs = self._dist_lut[actual_dists, r_clamped]

        self.belief = self._normalize(self.belief * (noise_probs * dist_probs))
        return self.belief

    def reset_after_capture(self) -> np.ndarray:
        self.belief = self.reset_prior.copy()
        return self.belief

    def apply_search_feedback(
        self, search_loc: tuple[int, int] | None, result: bool | None, is_self: bool = True
    ) -> np.ndarray:
        if search_loc is None or result is None:
            return self.belief

        if result:
            return self.reset_after_capture()

        if is_self:
            idx = _loc_to_idx(search_loc)
            self.belief[idx] = 0.0
            self.belief = self._normalize(self.belief)
        return self.belief

    def probability_at(self, loc: tuple[int, int]) -> float:
        return float(self.belief[_loc_to_idx(loc)])

    def topk(self, k: int) -> list[tuple[tuple[int, int], float]]:
        if k <= 0:
            return []
        order = np.argsort(-self.belief)
        result: list[tuple[tuple[int, int], float]] = []
        for idx in order[:k]:
            result.append((_idx_to_loc(int(idx)), float(self.belief[idx])))
        return result

    def entropy(self) -> float:
        """Shannon entropy of the current posterior in nats."""
        p = self.belief
        mask = p > 1e-12
        return float(-np.sum(p[mask] * np.log(p[mask])))

    def entropy_norm(self) -> float:
        """Entropy normalized to [0, 1] using log(N) as the max."""
        return self.entropy() / _LOG_N

    def noise_lut(self) -> np.ndarray:
        return self._noise_lut

    def dist_lut(self) -> np.ndarray:
        return self._dist_lut
