from __future__ import annotations

from game.board import Board

from .runtime_state import RuntimeState


class TimeManager:
    """Deterministic per-turn budget allocator with emergency fallback guard."""

    MIN_TURN_BUDGET = 0.015

    @staticmethod
    def compute_emergency_floor(initial_total_budget: float) -> float:
        return max(1.2, 0.02 * initial_total_budget)

    @staticmethod
    def profile_name(initial_total_budget: float) -> str:
        if initial_total_budget <= 260:
            return "strict_240"
        return "local_360"

    @staticmethod
    def phase_multiplier(turn_count: int) -> float:
        if turn_count < 20:
            return 1.25
        if turn_count < 60:
            return 1.10
        return 0.90

    @staticmethod
    def phase_cap(turn_count: int) -> float:
        if turn_count < 20:
            return 4.5
        if turn_count < 60:
            return 3.0
        return 1.5

    @classmethod
    def allocation(cls, board: Board, state: RuntimeState, time_remaining: float) -> tuple[float, bool]:
        turns_remaining = max(1, board.player_worker.turns_left)
        t_eff = max(0.0, time_remaining - state.emergency_floor_total)
        if t_eff <= 0:
            return 0.0, True

        base = t_eff / turns_remaining
        alloc_raw = base * cls.phase_multiplier(board.turn_count)
        alloc_raw = max(cls.MIN_TURN_BUDGET, min(alloc_raw, cls.phase_cap(board.turn_count)))
        allocation = min(alloc_raw, 0.20 * t_eff)

        return max(0.0, allocation), False
