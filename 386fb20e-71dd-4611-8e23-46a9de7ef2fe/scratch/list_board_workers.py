import sys
from pathlib import Path

# Add engine to sys.path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "engine"))

from game.board import Board

def list_board_attrs():
    board = Board()
    print(f"Board attributes: {dir(board)}")
    
    # Try common names
    for attr in ['worker_a', 'worker_b', 'p1_worker', 'p2_worker', 'workers']:
        if hasattr(board, attr):
            print(f"Found attribute: {attr}")

if __name__ == "__main__":
    list_board_attrs()
