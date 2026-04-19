import unittest
import numpy as np
import sys
import os
from pathlib import Path

# Add project root to sys.path so we can import from 'engine' and '3600-agents'
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "3600-agents") not in sys.path:
    sys.path.insert(0, str(ROOT / "3600-agents"))
if str(ROOT / "engine") not in sys.path:
    sys.path.insert(0, str(ROOT / "engine"))

from common import make_board, identity_transition
from Yolanda3_4.strategy.policy import PolicyEngine
from Yolanda3_4.tracking.belief import BeliefEngine
from Yolanda3_4.infra.runtime_state import RuntimeState
from game.enums import Cell, Direction, MoveType
from game.move import Move

class Yolanda3_4TrapRecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = PolicyEngine()
        self.belief = BeliefEngine(identity_transition())
        self.state = RuntimeState()
        self.board = make_board()

    def test_trap_low_ev_search_suppressed(self) -> None:
        """
        Verify that in a trap state, a low-EV search is suppressed in favor of recovery.
        Trap state: current=CARPET, no legal PRIME, d_space=2.
        """
        self.board.player_worker.position = (3, 3)
        self.board.player_worker.turns_left = 20
        self.board.set_cell((3, 3), Cell.CARPET)
        
        # Block neighbor SPACE cells to force dist_to_space >= 2
        # (3, 3) neighbors: (3, 4), (3, 2), (4, 3), (2, 3)
        for n in [(3, 4), (3, 2), (4, 3), (2, 3)]:
            self.board.set_cell(n, Cell.CARPET)
        
        # Now dist_to_space is at least 2 because we are surrounded by CARPET.
        # And we have no PRIMED neighbors to carpet, and no SPACE neighbors to prime.
        
        # Set a belief that gives a small positive EV.
        # 6 * p - 2 = 0.5  => 6p = 2.5 => p = 0.416
        self.belief.belief[:] = 0.0
        self.belief.belief[0] = 0.45 
        
        action = self.policy.select_action(
            self.board,
            self.belief,
            self.state,
            time_left=lambda: 120.0
        )
        
        # Should NOT be search
        self.assertNotEqual(action.move_type, MoveType.SEARCH)

    def test_trap_high_ev_search_allowed(self) -> None:
        """
        Verify that a high-EV search is still allowed even in a trap state.
        """
        self.board.player_worker.position = (3, 3)
        self.board.player_worker.turns_left = 20
        self.board.set_cell((3, 3), Cell.CARPET)
        for n in [(3, 4), (3, 2), (4, 3), (2, 3)]:
            self.board.set_cell(n, Cell.CARPET)
        
        # High EV: p = 0.9 => 6 * 0.9 - 2 = 3.4
        self.belief.belief[:] = 0.0
        self.belief.belief[0] = 0.9
        
        action = self.policy.select_action(
            self.board,
            self.belief,
            self.state,
            time_left=lambda: 120.0
        )
        
        self.assertEqual(action.move_type, MoveType.SEARCH)

    def test_trap_miss_streak_raises_threshold(self) -> None:
        """
        Verify that consecutive trap search misses raise the threshold for the next search.
        """
        self.board.player_worker.position = (3, 3)
        self.board.player_worker.turns_left = 20
        self.board.set_cell((3, 3), Cell.CARPET)
        for n in [(3, 4), (3, 2), (4, 3), (2, 3)]:
            self.board.set_cell(n, Cell.CARPET)

        # p = 0.9 => EV = 6 * 0.9 - 2 = 3.4
        self.belief.belief[:] = 0.0
        self.belief.belief[0] = 0.9
        
        # First attempt: should allowed (EV 1.6 > threshold ~0.6 + 0.6 = 1.2)
        # Note: we need to manually simulate the miss streak in state as we are calling select_action
        self.state.consecutive_trap_search_misses = 0
        
        action1 = self.policy.select_action(self.board, self.belief, self.state, time_left=lambda: 120.0)
        self.assertEqual(action1.move_type, MoveType.SEARCH)
        
        # Now simulate 3 misses. streak_penalty = 0.5 * 3 = 1.5. 
        # New threshold = baseline (~0.6) + trap_bonus (0.6) + streak (1.5) = 2.7.
        # EV 1.6 < 2.7, so it should be suppressed.
        self.state.consecutive_trap_search_misses = 3
        
        action2 = self.policy.select_action(self.board, self.belief, self.state, time_left=lambda: 120.0)
        self.assertNotEqual(action2.move_type, MoveType.SEARCH)

    def test_carpet_self_strand_penalized(self) -> None:
        """
        Verify that a carpet move that strands the agent (far from SPACE) is penalized
        compared to one that lands near SPACE.
        """
        # Setup: two possible carpet moves. One lands next to SPACE, one lands deep in CARPET.
        # This requires careful board setup.
        
        # Start at (2, 2)
        self.board.player_worker.position = (2, 2)
        self.board.player_worker.turns_left = 20
        
        # PRIMED path 1: (2, 3), (2, 4) - ends at (2, 4). (2, 5) is SPACE.
        self.board.set_cell((2, 3), Cell.PRIMED)
        self.board.set_cell((2, 4), Cell.PRIMED)
        self.board.set_cell((2, 5), Cell.SPACE)
        
        # PRIMED path 2: (3, 2), (4, 2) - ends at (4, 2). (5, 2), (4, 3) etc are CARPET.
        self.board.set_cell((3, 2), Cell.PRIMED)
        self.board.set_cell((4, 2), Cell.PRIMED)
        self.board.set_cell((5, 2), Cell.CARPET)
        self.board.set_cell((4, 3), Cell.CARPET)
        self.board.set_cell((4, 1), Cell.CARPET)

        move1 = Move.carpet(Direction.DOWN, 2) # lands at (2, 4)
        move2 = Move.carpet(Direction.RIGHT, 2) # lands at (4, 2)
        
        score1, _ = self.policy.score_non_search(self.board, move1, self.belief, self.state)
        score2, _ = self.policy.score_non_search(self.board, move2, self.belief, self.state)
        
        # Score 1 should be higher because (2, 4) is adjacent to SPACE (2, 5), 
        # while (4, 2) is surrounded by CARPET.
        self.assertGreater(score1, score2)

if __name__ == "__main__":
    unittest.main()
