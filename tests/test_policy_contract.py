from __future__ import annotations

import unittest
from unittest.mock import patch

import numpy as np

from common import identity_transition, make_board
from game.enums import Cell, Direction, MoveType
from game.move import Move
from Yolanda.tracking.belief import BeliefEngine
from Yolanda.tracking.opponent_observation import OpponentCategory
from Yolanda.strategy.policy import PolicyEngine
from Yolanda.infra.runtime_state import RuntimeState
from Yolanda.infra.time_manager import TimeManager


class PolicyContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.board = make_board()
        self.belief = BeliefEngine(identity_transition())
        self.policy = PolicyEngine()

    def test_explicit_search_candidates_are_present(self) -> None:
        # Keep search-prior concentrated so top-k search generation is deterministic.
        self.belief.belief = np.zeros(64, dtype=np.float64)
        self.belief.belief[0] = 1.0

        candidates = self.policy.generate_candidates(self.board, self.belief)
        self.assertTrue(any(m.move_type == MoveType.SEARCH for m in candidates))
        self.assertTrue(all(self.board.is_valid_move(m) for m in candidates))

    def test_parse_search_tuple_tristate(self) -> None:
        self.assertEqual(self.policy.parse_search_tuple((None, None)), (None, None))
        self.assertEqual(self.policy.parse_search_tuple(((1, 2), True)), ((1, 2), True))
        self.assertEqual(self.policy.parse_search_tuple(((1, 2), False)), ((1, 2), False))
        self.assertEqual(self.policy.parse_search_tuple(("bad", "bad")), (None, None))

    def test_apply_search_channels_obeys_tri_state_and_deduplicates(self) -> None:
        state = RuntimeState()
        self.belief.belief = np.full(64, 1.0 / 64.0, dtype=np.float64)

        # Unknown-result channel update must not perturb belief.
        board = make_board()
        board.player_search = ((1, 1), None)
        before = self.belief.belief.copy()
        self.policy.apply_search_channels(board, self.belief, state)
        self.assertTrue(np.allclose(before, self.belief.belief))

        # False-result update must eliminate searched location mass.
        board.player_search = ((0, 0), False)
        self.policy.apply_search_channels(board, self.belief, state)
        self.assertAlmostEqual(self.belief.probability_at((0, 0)), 0.0, places=8)

        # Replaying same channel tuple must be deduplicated.
        after_false = self.belief.belief.copy()
        self.policy.apply_search_channels(board, self.belief, state)
        self.assertTrue(np.allclose(after_false, self.belief.belief))

        # True-result update must reset belief to cached reset prior.
        board.opponent_search = ((2, 2), True)
        self.policy.apply_search_channels(board, self.belief, state)
        self.assertTrue(np.allclose(self.belief.belief, self.belief.reset_prior))

    def test_select_action_returns_valid_move_under_budget(self) -> None:
        state = RuntimeState()
        state.initial_total_budget = 240.0
        state.emergency_floor_total = TimeManager.compute_emergency_floor(240.0)

        action = self.policy.select_action(
            self.board,
            self.belief,
            state,
            time_left=lambda: 120.0,
        )

        self.assertTrue(self.board.is_valid_move(action))

    def test_score_search_is_six_p_minus_two(self) -> None:
        """assignment_spec §10.6: EV(search at c) = 6 * P(c) - 2."""
        self.belief.belief = np.zeros(64, dtype=np.float64)
        self.belief.belief[:] = 1.0 / 64.0
        loc = (2, 3)
        idx = loc[1] * 8 + loc[0]
        self.belief.belief[:] = 0.0
        self.belief.belief[idx] = 0.4
        smove = Move.search(loc)
        ev = self.policy.score_search(self.belief, smove)
        self.assertAlmostEqual(ev, 6.0 * 0.4 - 2.0, places=6)

    def test_score_search_positive_ev_threshold_one_third(self) -> None:
        """§10.6: positive EV when P(c) > 1/3."""
        loc = (1, 1)
        idx = loc[1] * 8 + loc[0]
        self.belief.belief = np.zeros(64, dtype=np.float64)
        self.belief.belief[idx] = 1.0 / 3.0 + 1e-6
        rest = (1.0 - self.belief.belief[idx]) / 63.0
        for i in range(64):
            if i != idx:
                self.belief.belief[i] = rest

        smove = Move.search(loc)
        self.assertGreater(self.policy.score_search(self.belief, smove), 0.0)

        self.belief.belief = np.zeros(64, dtype=np.float64)
        self.belief.belief[idx] = 1.0 / 3.0 - 1e-6
        rest2 = (1.0 - self.belief.belief[idx]) / 63.0
        for i in range(64):
            if i != idx:
                self.belief.belief[i] = rest2
        self.assertLessEqual(self.policy.score_search(self.belief, Move.search(loc)), 0.0)

    def test_prime_into_single_exit_is_vetoed(self) -> None:
        """§2.4/§6.3: prime moves requiring narrow dead-end entries are hard-vetoed."""
        board = make_board()
        board.player_worker.position = (3, 3)
        board.opponent_worker.position = (7, 7)
        board.set_cell((3, 1), Cell.BLOCKED)
        board.set_cell((2, 2), Cell.BLOCKED)

        tv, _ = self.policy.score_non_search(board, Move.prime(Direction.UP), self.belief, RuntimeState())
        self.assertEqual(tv, float("-inf"))

    def test_opening_phase_filters_carpet_actions(self) -> None:
        """§1.1: opening should prioritize infrastructure and avoid carpets."""
        board = make_board()
        board.player_worker.position = (3, 3)
        board.opponent_worker.position = (7, 7)
        board.player_worker.turns_left = 35
        for x in (4, 5, 6):
            board.set_cell((x, 3), Cell.PRIMED)

        action = self.policy.select_action(
            board,
            self.belief,
            RuntimeState(),
            time_left=lambda: 120.0,
        )
        self.assertNotEqual(action.move_type, MoveType.CARPET)

    def test_no_good_move_prefers_positive_ev_search(self) -> None:
        """§8.1: if non-search options are poor and search EV is positive, search."""
        board = make_board()
        board.player_worker.position = (1, 1)
        board.opponent_worker.position = (7, 7)
        board.player_worker.turns_left = 20
        board.set_cell((1, 1), Cell.CARPET)
        board.set_cell((1, 0), Cell.BLOCKED)
        board.set_cell((0, 1), Cell.BLOCKED)
        board.set_cell((1, 2), Cell.BLOCKED)

        self.belief.belief = np.zeros(64, dtype=np.float64)
        self.belief.belief[0] = 1.0

        action = self.policy.select_action(
            board,
            self.belief,
            RuntimeState(),
            time_left=lambda: 120.0,
        )
        self.assertEqual(action.move_type, MoveType.SEARCH)

    def test_can_extend_chain_requires_legal_one_turn_prime(self) -> None:
        """Extension check should require an actually legal one-turn prime extension."""
        board = make_board()
        board.player_worker.position = (2, 3)
        board.opponent_worker.position = (7, 7)
        for x in (3, 4, 5, 6):
            board.set_cell((x, 3), Cell.PRIMED)
        board.set_cell((1, 3), Cell.BLOCKED)  # blocks reverse-direction prime extension
        self.assertTrue(board.is_valid_move(Move.carpet(Direction.RIGHT, 4)))
        self.assertFalse(self.policy._can_extend_chain(board, Move.carpet(Direction.RIGHT, 4)))

    def test_phase_scaling_applied_before_adaptation(self) -> None:
        """§7.2: adaptation must consume phase-scaled bases, not raw bases."""
        board = make_board()
        board.player_worker.turns_left = 35  # opening phase
        state = RuntimeState()
        state.enable_opponent_model = True
        state.plies_as_player = 1  # _observe increments to even ply
        state.observed_turns = 6
        for _ in range(6):
            state.opp_turn_buffer.append((OpponentCategory.PRIME, 2))

        seen: dict[str, tuple[float, float, float, float]] = {}

        def _fake_apply(conf, raw, base_a, base_c, base_d, base_f):
            seen["bases"] = (base_a, base_c, base_d, base_f)
            return base_a, base_c, base_d, base_f

        with patch("Yolanda.strategy.policy.adaptation.apply_adaptation", side_effect=_fake_apply):
            _ = self.policy.select_action(board, self.belief, state, time_left=lambda: 120.0)

        self.assertIn("bases", seen)
        a, c, d, f = seen["bases"]
        self.assertAlmostEqual(a, self.policy.a * 0.9, places=6)
        self.assertAlmostEqual(c, self.policy.c * 1.2, places=6)
        self.assertAlmostEqual(d, self.policy.d * 0.5, places=6)
        self.assertAlmostEqual(f, self.policy.f * 1.2, places=6)

    def test_corridor_trap_vetoed_when_non_corridor_exists(self) -> None:
        """§6.2: corridor-trap moves are vetoed unless no alternative exists."""
        board = make_board()
        board.player_worker.position = (1, 1)
        board.opponent_worker.position = (7, 7)
        board.set_cell((0, 0), Cell.BLOCKED)
        board.set_cell((2, 0), Cell.BLOCKED)
        board.set_cell((0, 1), Cell.BLOCKED)
        board.set_cell((2, 1), Cell.BLOCKED)
        # This creates a trap on PLAIN(UP); PLAIN(DOWN) remains non-corridor.
        self.assertTrue(self.policy._is_corridor_trap_move(board, Move.plain(Direction.UP)))

        action = self.policy.select_action(board, self.belief, RuntimeState(), time_left=lambda: 120.0)
        self.assertFalse(action.move_type == MoveType.PLAIN and action.direction == Direction.UP)

    def test_no_good_fallback_prefers_prime_when_search_non_positive(self) -> None:
        """§8.1 order: with non-positive search EV, fallback should choose prime over plain."""
        board = make_board()
        state = RuntimeState()
        self.belief.belief = np.full(64, 1.0 / 64.0, dtype=np.float64)  # negative search EV
        bad_meta = {"mobility": 0.0, "immediate": 0.0, "risk": 1.3, "continuation": 0.0}
        with patch.object(self.policy, "score_non_search", return_value=(-1.0, bad_meta)):
            action = self.policy.select_action(board, self.belief, state, time_left=lambda: 120.0)
        self.assertEqual(action.move_type, MoveType.PRIME)

    def test_standard_gate_uses_best_non_search_immediate(self) -> None:
        """§9.1: Q_best_non must come from selected best non-search action."""
        board = make_board()
        board.player_worker.position = (3, 3)
        board.opponent_worker.position = (7, 7)
        board.player_worker.turns_left = 20
        for x in (4, 5, 6):
            board.set_cell((x, 3), Cell.PRIMED)

        # Make search EV positive enough to beat threshold including heuristic surplus.
        # effective_q = 0.0 + 0.5 * 10.0 = 5.0; margin = 0.4. Need EV >= 5.4.
        # 6 * p - 2 >= 5.4 => 6p >= 7.4 => p >= 1.23 (Impossible).
        # We need to lower the mock tv to make search viable in this test.
        def _stub_score_non_search(board_in, mv, belief_in, state_in):
            if mv.move_type == MoveType.PLAIN:
                return 2.0, {"mobility": 4.0, "immediate": 0.0, "risk": 0.0, "continuation": 0.0}
            if mv.move_type == MoveType.CARPET:
                return 1.0, {"mobility": 2.0, "immediate": float(mv.roll_length), "risk": 0.0, "continuation": 0.0}
            return 0.0, {"mobility": 3.0, "immediate": 1.0, "risk": 0.0, "continuation": 0.0}

        # Search EV with p=0.7: 6 * 0.7 - 2 = 2.2.
        # effective_q = 0.0 + 0.5 * 2.0 = 1.0. margin = 0.4.
        # 2.2 >= 1.4. Should SEARCH.
        self.belief.belief = np.zeros(64, dtype=np.float64)
        self.belief.belief[0] = 0.7

        with patch.object(self.policy, "score_non_search", side_effect=_stub_score_non_search):
            action = self.policy.select_action(board, self.belief, RuntimeState(), time_left=lambda: 120.0)
        self.assertEqual(action.move_type, MoveType.SEARCH)

    def test_late_phase_prioritizes_adjacent_carpet_ge_three(self) -> None:
        """§1.3: in late phase, adjacent carpet chains >=3 are converted immediately."""
        board = make_board()
        board.player_worker.position = (2, 3)
        board.opponent_worker.position = (7, 7)
        board.player_worker.turns_left = 8  # late phase
        for x in (3, 4, 5):
            board.set_cell((x, 3), Cell.PRIMED)
        self.belief.belief = np.full(64, 1.0 / 64.0, dtype=np.float64)
        action = self.policy.select_action(board, self.belief, RuntimeState(), time_left=lambda: 120.0)
        self.assertEqual(action.move_type, MoveType.CARPET)
        self.assertGreaterEqual(action.roll_length, 3)




if __name__ == "__main__":
    unittest.main()
