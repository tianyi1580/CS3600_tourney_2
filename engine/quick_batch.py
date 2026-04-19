#!/usr/bin/env python3
"""Quick batch evaluator for Yolanda3_5 vs Yolanda3_4.

Usage: python3 quick_batch.py [N_GAMES] [AGENT_A] [AGENT_B]
"""
import multiprocessing
import os
import sys
import pathlib
import time


def main():
    sys.path.insert(0, str(pathlib.Path(__file__).parent.resolve()))
    from gameplay import play_game

    TOP = str(pathlib.Path(__file__).parent.parent.resolve())
    PD = os.path.join(TOP, "3600-agents")

    GAMES = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    AGENT_A = sys.argv[2] if len(sys.argv) > 2 else "Yolanda3_5"
    AGENT_B = sys.argv[3] if len(sys.argv) > 3 else "Yolanda3_4"

    wins_a = 0
    wins_b = 0
    ties = 0
    crashes = 0
    timeouts = 0

    batch_start = time.perf_counter()

    for i in range(GAMES):
        # Alternate sides
        if i % 2 == 0:
            slot_a, slot_b = AGENT_A, AGENT_B
        else:
            slot_a, slot_b = AGENT_B, AGENT_A

        try:
            final_board, *_ = play_game(
                PD, PD, slot_a, slot_b,
                display_game=False, delay=0.0,
                clear_screen=False, record=False,
                limit_resources=False,
            )

            winner = final_board.winner  # ResultArbiter: PLAYER_A=0, PLAYER_B=1, TIE=2

            win_reason = getattr(final_board, 'win_reason', 'POINTS')
            if hasattr(win_reason, 'name'):
                win_reason = win_reason.name
            if str(win_reason) in ('TIMEOUT', '1'):
                timeouts += 1

            # Map engine winner back to our agent names
            if winner == 0:  # PLAYER_A wins
                engine_winner = slot_a
            elif winner == 1:  # PLAYER_B wins
                engine_winner = slot_b
            else:
                engine_winner = "TIE"

            if engine_winner == AGENT_A:
                wins_a += 1
                result_str = f"{AGENT_A} WIN"
            elif engine_winner == AGENT_B:
                wins_b += 1
                result_str = f"{AGENT_B} WIN"
            else:
                ties += 1
                result_str = "TIE"

            print(f"Game {i+1:3d}: {result_str:15s} | {win_reason} | Sides: SlotA={slot_a} SlotB={slot_b}")

        except Exception as e:
            crashes += 1
            print(f"Game {i+1:3d}: CRASH — {e}")

    elapsed = time.perf_counter() - batch_start
    played = wins_a + wins_b + ties
    print(f"\n{'='*70}")
    print(f"BATCH RESULTS: {AGENT_A} vs {AGENT_B} ({GAMES} games, {elapsed:.1f}s)")
    print(f"{'='*70}")
    print(f"  {AGENT_A} wins: {wins_a}/{played} ({100*wins_a/max(1,played):.1f}%)")
    print(f"  {AGENT_B} wins: {wins_b}/{played} ({100*wins_b/max(1,played):.1f}%)")
    print(f"  Ties:          {ties}/{played}")
    print(f"  Crashes:       {crashes}")
    print(f"  Timeouts:      {timeouts}")


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
