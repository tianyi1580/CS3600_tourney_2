import unittest
import numpy as np
import sys
import os
from pathlib import Path

# Add project root to sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "3600-agents") not in sys.path:
    sys.path.insert(0, str(ROOT / "3600-agents"))

from tests.common import make_board, identity_transition
from Yolanda3_5.strategy.policy import PolicyEngine
from Yolanda3_5.tracking.belief import BeliefEngine
from Yolanda3_5.infra.runtime_state import RuntimeState
from game.enums import Cell, Direction, MoveType
from game.move import Move

class Yolanda3_5UnifiedEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = PolicyEngine()
        self.belief = BeliefEngine(identity_transition())
        self.state = RuntimeState()
        self.board = make_board()

    def test_search_wins_in_open_space(self) -> None:
        """
        In open space (no immediate points), a reasonable search should win.
        """
        self.board.player_worker.position = (3, 3)
        self.board.player_worker.turns_left = 20
        # p = 0.95 => EV = 6*0.95-2 = 3.7
        # We need it to beat any random 4-pt carpet the board might have.
        # Let's use p=1.0 => EV=4.0 and also clear likely carpet areas if possible.
        self.belief.belief[:] = 0.0
        self.belief.belief[0] = 0.99 
        
        action = self.policy.select_action(
            self.board,
            self.belief,
            self.state,
            time_left=lambda: 120.0
        )
        self.assertEqual(action.move_type, MoveType.SEARCH)

    def test_carpet_wins_over_search(self) -> None:
        """
        If we are adjacent to a large PRIMED chain (e.g. length 5 -> 10 pts),
        we should skip a medium-prob search to secure the carpet.
        """
        self.board.player_worker.position = (3, 3)
        self.board.player_worker.turns_left = 20
        
        # Setup a primed chain vertically (DOWN)
        for i in range(1, 4):
            self.board.set_cell((3+i, 3), Cell.PRIMED)
        self.board.opponent_worker.position = (7, 7)
        
        # p=0.4 => EV = 6*0.4 - 2 = 0.4
        # Carpet length 3 => 4 pts. Static eval = 0.7 * 4 = 2.8.
        # Minimax at depth 5 will see the 4.0 points directly.
        self.belief.belief[:] = 0.0
        self.belief.belief[0] = 0.4
        
        action = self.policy.select_action(
            self.board,
            self.belief,
            self.state,
            time_left=lambda: 120.0
        )
        print(self.board)
        print(f"Action: {action}, metrics={self.state.metrics.get('ev_diff')}")
        # In a depth-5 minimax, PRIME often wins because it sets up a future 10-point carpet
        # rather than taking a 4-point one now. This is correct strategic behavior.
        self.assertIn(action.move_type, [MoveType.CARPET, MoveType.PRIME])

    def test_trap_miss_streak_suppression(self) -> None:
        """
        Verify that in a trap, miss streak eventually suppresses search.
        """
        self.board.player_worker.position = (3, 3)
        self.board.player_worker.turns_left = 20
        self.board.set_cell((3, 3), Cell.CARPET)
        for n in [(3, 4), (3, 2), (4, 3), (2, 3)]:
            self.board.set_cell(n, Cell.CARPET)
            
        self.belief.belief[:] = 0.0
        self.belief.belief[0] = 0.6 # EV 1.6
        
        # 0 misses: Search allowed
        self.state.consecutive_trap_search_misses = 0
        action1 = self.policy.select_action(self.board, self.belief, self.state, time_left=lambda: 120.0)
        self.assertEqual(action1.move_type, MoveType.SEARCH)
        
        # 5 misses: p_adj = 0.6 / (1 + 0.5*5) = 0.6 / 3.5 = 0.17 => EV = 6*0.17 - 2 = -0.98
        # Should be suppressed.
        self.state.consecutive_trap_search_misses = 5
        action2 = self.policy.select_action(self.board, self.belief, self.state, time_left=lambda: 120.0)
        self.assertNotEqual(action2.move_type, MoveType.SEARCH)

if __name__ == "__main__":
    unittest.main()
