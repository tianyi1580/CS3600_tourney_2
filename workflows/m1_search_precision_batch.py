#!/usr/bin/env python3
"""
M1 search-precision batch: Yolanda vs RandomSearchBaseline under strict_240
(play_game with limit_resources=True => 240s budget).

Aggregates search attempts / correct hits from board history (even half-moves
= player A, odd = player B).
"""
from __future__ import annotations

import argparse
import os
import platform
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _stats_player_a(board) -> tuple[int, int]:
    from game.enums import MoveType

    lb = board.history.left_behind_enums
    rc = board.history.rat_caught
    attempts = correct = 0
    for i, mt in enumerate(lb):
        if i % 2 != 0:
            continue
        if mt != MoveType.SEARCH:
            continue
        attempts += 1
        if rc[i]:
            correct += 1
    return attempts, correct


def _stats_player_b(board) -> tuple[int, int]:
    from game.enums import MoveType

    lb = board.history.left_behind_enums
    rc = board.history.rat_caught
    attempts = correct = 0
    for i, mt in enumerate(lb):
        if i % 2 != 1:
            continue
        if mt != MoveType.SEARCH:
            continue
        attempts += 1
        if rc[i]:
            correct += 1
    return attempts, correct


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=12, help="Games per pairing (each game swaps sides once)")
    parser.add_argument("--seed-start", type=int, default=42, help="Base seed for board randomness")
    parser.add_argument(
        "--limit-resources",
        action=argparse.BooleanOptionalAction,
        default=platform.system() == "Linux",
        help="Engine resource limits (often fails on macOS RLIMIT_RSS; default True on Linux only)",
    )
    parser.add_argument(
        "--play-time",
        type=int,
        default=240,
        help="Total per-player clock budget passed to Board (strict_240 gate)",
    )
    args = parser.parse_args()

    sys.path.insert(0, str(ROOT / "engine"))
    sys.path.insert(0, str(ROOT / "3600-agents"))
    from game.enums import ResultArbiter
    from gameplay import play_game

    play_dir = os.path.join(str(ROOT), "3600-agents")

    y_att = y_cor = r_att = r_cor = 0
    y_wins = ties = 0

    for g in range(args.games):
        random.seed(args.seed_start + g)
        yolanda_is_a = (g % 2 == 0)
        if yolanda_is_a:
            board, *_ = play_game(
                play_dir,
                play_dir,
                "Yolanda",
                "RandomSearchBaseline",
                display_game=False,
                delay=0,
                clear_screen=False,
                record=True,
                limit_resources=args.limit_resources,
                play_time_override=args.play_time,
            )
            a_a, a_c = _stats_player_a(board)
            b_a, b_c = _stats_player_b(board)
            y_att += a_a
            y_cor += a_c
            r_att += b_a
            r_cor += b_c
        else:
            board, *_ = play_game(
                play_dir,
                play_dir,
                "RandomSearchBaseline",
                "Yolanda",
                display_game=False,
                delay=0,
                clear_screen=False,
                record=True,
                limit_resources=args.limit_resources,
                play_time_override=args.play_time,
            )
            a_a, a_c = _stats_player_a(board)
            b_a, b_c = _stats_player_b(board)
            y_att += b_a
            y_cor += b_c
            r_att += a_a
            r_cor += a_c

        w = board.winner
        if w == ResultArbiter.TIE:
            ties += 1
        elif (w == ResultArbiter.PLAYER_A and yolanda_is_a) or (
            w == ResultArbiter.PLAYER_B and not yolanda_is_a
        ):
            y_wins += 1

    def rate(num: int, den: int) -> float:
        return float(num) / den if den else 0.0

    print(
        f"M1 search precision batch (play_time={args.play_time}, "
        f"limit_resources={args.limit_resources})"
    )
    print(f"games={args.games} seed_start={args.seed_start}")
    print(
        f"Yolanda search: attempts={y_att} correct={y_cor} "
        f"precision={rate(y_cor, y_att):.4f}"
    )
    print(
        f"RandomSearchBaseline search: attempts={r_att} correct={r_cor} "
        f"precision={rate(r_cor, r_att):.4f}"
    )
    print(f"Yolanda wins={y_wins} ties={ties} baseline_wins={args.games - y_wins - ties}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
