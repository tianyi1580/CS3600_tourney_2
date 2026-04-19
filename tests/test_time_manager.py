from __future__ import annotations

import unittest

from common import make_board
from Yolanda.infra.runtime_state import RuntimeState
from Yolanda.infra.time_manager import TimeManager


class TimeManagerTests(unittest.TestCase):
    def test_profile_name_strict_and_local(self) -> None:
        self.assertEqual(TimeManager.profile_name(240.0), "strict_240")
        self.assertEqual(TimeManager.profile_name(360.0), "local_360")

    def test_allocation_respects_emergency_and_non_negative(self) -> None:
        board = make_board(time_to_play=240)
        state = RuntimeState(initial_total_budget=240.0)
        state.emergency_floor_total = TimeManager.compute_emergency_floor(240.0)

        alloc, emergency = TimeManager.allocation(board, state, time_remaining=120.0)
        self.assertFalse(emergency)
        self.assertGreaterEqual(alloc, 0.0)
        self.assertLessEqual(alloc, 0.2 * (120.0 - state.emergency_floor_total) + 1e-9)

    def test_allocation_enters_emergency_near_floor(self) -> None:
        board = make_board(time_to_play=240)
        state = RuntimeState(initial_total_budget=240.0)
        state.emergency_floor_total = 3.0

        alloc, emergency = TimeManager.allocation(board, state, time_remaining=2.9)
        self.assertTrue(emergency)
        self.assertEqual(alloc, 0.0)

    def test_phase_multiplier_boundaries(self) -> None:
        self.assertEqual(TimeManager.phase_multiplier(19), 1.25)
        self.assertEqual(TimeManager.phase_multiplier(20), 1.10)
        self.assertEqual(TimeManager.phase_multiplier(59), 1.10)
        self.assertEqual(TimeManager.phase_multiplier(60), 0.90)

    def test_phase_cap_boundaries(self) -> None:
        self.assertEqual(TimeManager.phase_cap(19), 4.5)
        self.assertEqual(TimeManager.phase_cap(20), 3.0)
        self.assertEqual(TimeManager.phase_cap(59), 3.0)
        self.assertEqual(TimeManager.phase_cap(60), 1.5)

    def test_allocation_respects_phase_cap_and_antiburn(self) -> None:
        board = make_board(time_to_play=240)
        board.turn_count = 0
        board.player_worker.turns_left = 1
        state = RuntimeState(initial_total_budget=240.0)
        state.emergency_floor_total = TimeManager.compute_emergency_floor(240.0)
        t_rem = 200.0
        t_eff = t_rem - state.emergency_floor_total

        alloc, emergency = TimeManager.allocation(board, state, time_remaining=t_rem)
        self.assertFalse(emergency)
        self.assertLessEqual(alloc, TimeManager.phase_cap(0) + 1e-9)
        self.assertLessEqual(alloc, 0.2 * t_eff + 1e-9)

    def test_allocation_min_turn_budget_when_base_is_tiny(self) -> None:
        board = make_board(time_to_play=240)
        board.turn_count = 0
        board.player_worker.turns_left = 100
        state = RuntimeState(initial_total_budget=240.0)
        state.emergency_floor_total = TimeManager.compute_emergency_floor(240.0)
        t_rem = state.emergency_floor_total + 0.5
        t_eff = 0.5

        alloc, emergency = TimeManager.allocation(board, state, time_remaining=t_rem)
        self.assertFalse(emergency)
        self.assertGreaterEqual(alloc, TimeManager.MIN_TURN_BUDGET - 1e-9)
        self.assertLessEqual(alloc, 0.2 * t_eff + 1e-9)

    def test_t_eff_zero_triggers_emergency(self) -> None:
        board = make_board(time_to_play=240)
        state = RuntimeState(initial_total_budget=240.0)
        state.emergency_floor_total = TimeManager.compute_emergency_floor(240.0)

        alloc, emergency = TimeManager.allocation(board, state, time_remaining=state.emergency_floor_total)
        self.assertTrue(emergency)
        self.assertEqual(alloc, 0.0)

    def test_mid_phase_uses_mid_cap(self) -> None:
        board = make_board(time_to_play=240)
        board.turn_count = 40
        board.player_worker.turns_left = 1
        state = RuntimeState(initial_total_budget=240.0)
        state.emergency_floor_total = TimeManager.compute_emergency_floor(240.0)

        alloc, emergency = TimeManager.allocation(board, state, time_remaining=150.0)
        self.assertFalse(emergency)
        self.assertLessEqual(alloc, 3.0 + 1e-9)


if __name__ == "__main__":
    unittest.main()
