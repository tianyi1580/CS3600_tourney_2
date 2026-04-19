import sys
from pathlib import Path

# Add engine to sys.path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "engine"))

from game.board import Board

def check_perspective_swap():
    board = Board()
    board.player_worker.position = (0, 0)
    board.opponent_worker.position = (7, 7)
    print(f"Start: Player is A={board.is_player_a_turn}")
    
    # Get a valid move
    moves = board.get_valid_moves(exclude_search=True)
    if not moves:
        print("No moves!")
        return
    
    mv = moves[0]
    board_after = board.forecast_move(mv)
    print(f"After move: Player is A={board_after.is_player_a_turn}")
    
    # Check if workers swapped
    # In this engine, player_worker always refers to the worker whose turn it is.
    # So if turn swapped, board_after.player_worker should be the one who was opponent_worker before.
    print(f"Original player pos: {board.player_worker.get_location()}")
    print(f"Original opponent pos: {board.opponent_worker.get_location()}")
    print(f"BoardAfter player pos: {board_after.player_worker.get_location()}")
    
    if board_after.player_worker.get_location() == board.opponent_worker.get_location():
        print("YES! Perspective swaps automatically on forecast_move.")
    else:
        print("NO! Perspective stays the same. Manual reverse needed.")

if __name__ == "__main__":
    check_perspective_swap()
