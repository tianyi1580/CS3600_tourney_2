from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from game.board import Board
from game.enums import BOARD_SIZE, Noise
from game.rat import DISTANCE_ERROR_OFFSETS, DISTANCE_ERROR_PROBS, NOISE_PROBS


def _idx_to_loc(idx: int) -> tuple[int, int]:
    return (idx % BOARD_SIZE, idx // BOARD_SIZE)


def _loc_to_idx(loc: tuple[int, int]) -> int:
    return loc[1] * BOARD_SIZE + loc[0]


@dataclass
class BeliefEngine:
    """Tracks rat posterior over all 64 cells."""

    transition_matrix: np.ndarray

    def __post_init__(self) -> None:
        t = np.asarray(self.transition_matrix, dtype=np.float64)
        if t.shape != (BOARD_SIZE * BOARD_SIZE, BOARD_SIZE * BOARD_SIZE):
            raise ValueError(f"Expected 64x64 transition matrix, got {t.shape}")
        row_sum = t.sum(axis=1, keepdims=True)
        row_sum[row_sum == 0.0] = 1.0
        self.transition_matrix = t / row_sum
        self.transition_matrix_2 = self.transition_matrix @ self.transition_matrix

        start = np.zeros(BOARD_SIZE * BOARD_SIZE, dtype=np.float64)
        start[0] = 1.0
        self.reset_prior = start @ np.linalg.matrix_power(self.transition_matrix, 1000)
        self.belief = self.reset_prior.copy()

    def _normalize(self, vec: np.ndarray) -> np.ndarray:
        s = float(np.sum(vec))
        if s <= 0:
            return np.full_like(vec, 1.0 / len(vec), dtype=np.float64)
        
        # Center-bias normalization: slightly boost probability towards the board center (3.5, 3.5)
        # to counteract the natural diffusion of the transition matrix.
        centered_vec = vec / s
        for idx in range(BOARD_SIZE * BOARD_SIZE):
            loc = _idx_to_loc(idx)
            dist_to_center = abs(loc[0] - 3.5) + abs(loc[1] - 3.5)
            # Apply a very small exponential bias towards center
            centered_vec[idx] *= np.exp(-0.02 * dist_to_center)
            
        final_sum = float(np.sum(centered_vec))
        return centered_vec / final_sum

    def predict(self, use_single_step: bool, opp_miss_cell: tuple[int, int] | None) -> np.ndarray:
        if opp_miss_cell is not None:
            # If opponent missed, zero that cell before EACH transition step 
            # to properly account for two rat moves.
            idx = _loc_to_idx(opp_miss_cell)
            
            # Step 1
            self.belief = self._normalize(self.belief @ self.transition_matrix)
            self.belief[idx] = 0.0
            self.belief = self._normalize(self.belief)
            
            # Step 2
            if not use_single_step:
                self.belief = self._normalize(self.belief @ self.transition_matrix)
                self.belief[idx] = 0.0
                self.belief = self._normalize(self.belief)
        else:
            if use_single_step:
                self.belief = self._normalize(self.belief @ self.transition_matrix)
            else:
                self.belief = self._normalize(self.belief @ self.transition_matrix_2)
        return self.belief

    def _distance_likelihood(self, actual_distance: int, reported_distance: int) -> float:
        p = 0.0
        for offset, prob in zip(DISTANCE_ERROR_OFFSETS, DISTANCE_ERROR_PROBS):
            if max(0, actual_distance + offset) == reported_distance:
                p += prob
        return p

    def update(self, noise: Noise, estimated_distance: int, board: Board) -> np.ndarray:
        worker_loc = board.player_worker.get_location()
        likelihood = np.zeros(BOARD_SIZE * BOARD_SIZE, dtype=np.float64)

        for idx in range(BOARD_SIZE * BOARD_SIZE):
            loc = _idx_to_loc(idx)
            cell_type = board.get_cell(loc)
            noise_prob = NOISE_PROBS[cell_type][int(noise)]
            actual_dist = abs(worker_loc[0] - loc[0]) + abs(worker_loc[1] - loc[1])
            dist_prob = self._distance_likelihood(actual_dist, int(estimated_distance))
            likelihood[idx] = noise_prob * dist_prob

        self.belief = self._normalize(self.belief * likelihood)
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
