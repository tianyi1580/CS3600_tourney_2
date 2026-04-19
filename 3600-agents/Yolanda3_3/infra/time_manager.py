from __future__ import annotations

from game.board import Board

from .runtime_state import RuntimeState


class TimeManager:
    """Deterministic per-turn budget allocator with emergency fallback guard."""

    MIN_TURN_BUDGET = 0.015

    @staticmethod
    def compute_emergency_floor(initial_total_budget: float) -> float:
        return max(0.8, 0.015 * initial_total_budget)

    @staticmethod
    def profile_name(initial_total_budget: float) -> str:
        if initial_total_budget <= 260:
            return "strict_240"
        return "local_360"

    @staticmethod
    def phase_multiplier(turn_count: int) -> float:
        if turn_count < 20:
            return 1.80
        if turn_count < 60:
            return 1.40
        return 1.00

    @staticmethod
    def phase_cap(turn_count: int) -> float:
        if turn_count < 20:
            return 8.0
        if turn_count < 60:
            return 6.0
        return 3.0

    @classmethod
    def allocation(cls, board: Board, state: RuntimeState, time_remaining: float) -> tuple[float, bool]:
        turns_remaining = max(1, board.player_worker.turns_left)
        t_eff = max(0.0, time_remaining - state.emergency_floor_total)
        if t_eff <= 0:
            return 0.0, True

        base = t_eff / turns_remaining
        alloc_raw = base * cls.phase_multiplier(board.turn_count)
        alloc_raw = max(cls.MIN_TURN_BUDGET, min(alloc_raw, cls.phase_cap(board.turn_count)))
        allocation = min(alloc_raw, 0.30 * t_eff)

        return max(0.0, allocation), False

    @classmethod
    def deep_path_plan(
        cls,
        board: Board,
        state: RuntimeState,
        time_remaining: float,
        turn_allocation: float,
    ) -> tuple[bool, int]:
        """Return (enable_deep_path, top_k) for per-turn tactical deep evaluation."""
        turns_remaining = max(1, board.player_worker.turns_left)
        t_eff = max(0.0, time_remaining - state.emergency_floor_total)
        if t_eff <= 0 or turn_allocation <= 0:
            return False, 0

        reserve_after_min = t_eff - turns_remaining * cls.MIN_TURN_BUDGET
        if board.turn_count < 20:
            base_k = 8
        elif board.turn_count < 60:
            base_k = 6
        else:
            base_k = 4

        if turn_allocation >= 0.08 and reserve_after_min >= 0.50 and board.player_worker.turns_left > 4:
            return True, base_k
        if turn_allocation >= 0.04 and reserve_after_min >= 0.25 and board.player_worker.turns_left > 2:
            return True, max(3, base_k - 2)
        return False, 0
