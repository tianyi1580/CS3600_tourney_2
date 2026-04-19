import sys
import time
from pathlib import Path

# Add engine and agents to sys.path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "engine"))
sys.path.insert(0, str(ROOT / "3600-agents"))

from game.board import Board
from game.move import Move, MoveType
from Yolanda3_5.strategy.lookahead import Lookahead
from Yolanda3_5.strategy.policy import PolicyEngine
from Yolanda3_5.tracking.belief import BeliefEngine
from Yolanda3_5.infra.runtime_state import RuntimeState

def debug_unified_engine():
    board = Board()
    board.player_worker.position = (3, 3)
    board.opponent_worker.position = (4, 4)
    import numpy as np
    tmat = np.eye(64)
    belief = BeliefEngine(transition_matrix=tmat)
    belief.belief[:] = 0.0
    # Location (0,0) has p=0.05 (Noise)
    belief.belief[0] = 0.05
    # Location (7,7) has p=0.05
    belief.belief[63] = 0.05
    
    state = RuntimeState()
    policy = PolicyEngine()
    
    lookahead = Lookahead(policy)
    
    # Candidates: PLAIN moves
    candidates = board.get_valid_moves(exclude_search=True)
    # Search candidates: (0,0) and (7,7)
    search_candidates = [
        (Move.search((0, 0)), 0.05),
        (Move.search((7, 7)), 0.05)
    ]
    
    print("Starting rank_moves...")
    best_move, value, completed = lookahead.rank_moves(
        board,
        candidates,
        search_candidates,
        time_budget_s=1.0
    )
    
    print(f"Result: Best={best_move}, Value={value:.2f}")
    if best_move and best_move.move_type == MoveType.SEARCH:
        print("FAIL: Search won with p=0.05!")
    else:
        print("SUCCESS: Movement correctly preferred over noise search.")

if __name__ == "__main__":
    debug_unified_engine()
