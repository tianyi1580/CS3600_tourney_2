"""Yolanda Prime v3 time manager.

The single most important change vs v2: we actually *use the full 240 s* match
budget by (a) dropping the per-phase cap, (b) applying a complexity multiplier
to per-turn allocation, and (c) exposing a soft/hard deadline pair for the
iterative-deepening search.

Allocation:
    base            = (time_left − reserve) / turns_remaining
    phase_mult      = {opening 1.8, mid 1.6, late 1.2}        (weights-tunable)
    complexity_mult = f(root_branching, top2_gap, voronoi_contest, belief_peak)
    alloc           = base · phase_mult · complexity_mult
                      bounded by alloc ≤ fraction_cap · (time_left − reserve)

The soft deadline is `start + alloc`; the hard deadline is `start + alloc·1.15`
so the ID loop can finish the currently-running ply without blowing the budget."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from game.board import Board

from .runtime_state import RuntimeState


@dataclass(frozen=True)
class Deadlines:
    soft: float
    hard: float


@dataclass
class ComplexitySignals:
    """Signals the orchestrator collects and feeds into the time manager."""

    root_branching: int = 0       # 0..16+
    top2_gap: float = 0.0         # 0 = close call, large = trivial decision
    contested_count: int = 0      # Voronoi-contested cells
    belief_peak: float = 0.0      # 0..1 — high = decisive search opportunity
    recovery_mode: str = "neutral"  # "panic" spikes time; "cautious" normal


class TimeManager:
    MIN_TURN_BUDGET = 0.050
    HARD_OVERAGE = 1.15

    @staticmethod
    def compute_emergency_floor(initial_total_budget: float) -> float:
        return max(0.8, 0.015 * initial_total_budget)

    @staticmethod
    def profile_name(initial_total_budget: float) -> str:
        if initial_total_budget <= 260:
            return "strict_240"
        return "local_360"

    @staticmethod
    def phase(turn_count: int) -> str:
        if turn_count < 20:
            return "opening"
        if turn_count < 60:
            return "mid"
        return "late"

    @classmethod
    def phase_multiplier(cls, turn_count: int, weights: dict) -> float:
        phase = cls.phase(turn_count)
        if phase == "opening":
            return float(weights.get("time_opening_multiplier", 1.8))
        if phase == "mid":
            return float(weights.get("time_mid_multiplier", 1.6))
        return float(weights.get("time_late_multiplier", 1.2))

    @classmethod
    def complexity_multiplier(
        cls, signals: ComplexitySignals, weights: dict
    ) -> float:
        """Combine signals into a scalar multiplier in [time_complex_min, time_complex_max].

        Each signal contributes a linear component bounded to a small range;
        clamped at the end."""
        lo = float(weights.get("time_complex_min", 0.7))
        hi = float(weights.get("time_complex_max", 1.6))
        m = 1.0

        # Root branching: more moves -> scales up, diminishing returns.
        if signals.root_branching >= 10:
            m *= 1.20
        elif signals.root_branching >= 6:
            m *= 1.08
        elif signals.root_branching <= 2:
            m *= 0.80

        # Close race at the top of the move list: spend more.
        if signals.top2_gap < 0.5:
            m *= 1.20
        elif signals.top2_gap > 3.0:
            m *= 0.85

        # Voronoi contest: spending time resolving contested cells pays off.
        if signals.contested_count >= 6:
            m *= 1.15
        elif signals.contested_count >= 3:
            m *= 1.05

        # High belief peak = search decision is critical.
        if signals.belief_peak >= 0.35:
            m *= 1.20
        elif signals.belief_peak >= 0.15:
            m *= 1.05

        # Recovery spike.
        if signals.recovery_mode == "panic":
            m *= 1.30
        elif signals.recovery_mode == "cautious":
            m *= 0.95

        if m < lo:
            m = lo
        if m > hi:
            m = hi
        return m

    @classmethod
    def allocation(
        cls,
        board: Board,
        state: RuntimeState,
        time_remaining: float,
        weights: Optional[dict] = None,
        *,
        complexity_mult: float = 1.0,
    ) -> tuple[float, bool]:
        w = weights or {}
        reserve = float(w.get("time_reserve", 5.0))
        fraction_cap = float(w.get("time_fraction_cap", 0.25))

        t_eff = max(0.0, time_remaining - max(reserve, state.emergency_floor_total))
        if t_eff <= 0:
            return 0.0, True

        turns_remaining = max(1, board.player_worker.turns_left)
        base = t_eff / turns_remaining
        phase_mult = cls.phase_multiplier(board.turn_count, w)
        alloc_raw = base * phase_mult * max(0.1, complexity_mult)
        alloc = min(alloc_raw, fraction_cap * t_eff)
        alloc = max(cls.MIN_TURN_BUDGET, alloc)
        return alloc, False

    @classmethod
    def deadlines(cls, start_monotonic: float, alloc: float) -> Deadlines:
        return Deadlines(
            soft=start_monotonic + alloc,
            hard=start_monotonic + alloc * cls.HARD_OVERAGE,
        )
