#!/usr/bin/env python3
"""
M2 competitive batch: Yolanda vs RandomSearchBaseline.

Aggregates wins, score deltas, search stats, and reliability outcomes
(timeout / invalid / crash) under strict_240 or local_360-style budgets.
"""
from __future__ import annotations

import argparse
import contextlib
import io
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


def _absolute_ab_scores(board) -> tuple[int, int]:
    """Return (player_A_points, player_B_points) in arbiter frame."""
    if board.player_worker.is_player_a:
        return board.player_worker.get_points(), board.opponent_worker.get_points()
    return board.opponent_worker.get_points(), board.player_worker.get_points()


def _yolanda_lost_ab(yolanda_is_a: bool, winner) -> bool:
    from game.enums import ResultArbiter

    if winner == ResultArbiter.TIE or winner == ResultArbiter.ERROR:
        return False
    if yolanda_is_a:
        return winner == ResultArbiter.PLAYER_B
    return winner == ResultArbiter.PLAYER_A


def synthetic_allocation_table(profile_budget: float) -> str:
    """Markdown fragment: theoretical allocations over a time/turn grid (bot_plan v4 formula)."""
    sys.path.insert(0, str(ROOT / "engine"))
    sys.path.insert(0, str(ROOT / "3600-agents"))
    from game.board import Board
    from Yolanda.runtime_state import RuntimeState
    from Yolanda.time_manager import TimeManager

    lines = [
        f"### Synthetic sweep: initial_budget={profile_budget} ({TimeManager.profile_name(profile_budget)})",
        "",
        "| turn_count | phase | t_rem | turns_left | alloc (s) | emergency |",
        "| --- | --- | --- | --- | --- | --- |",
    ]

    state = RuntimeState(initial_total_budget=profile_budget)
    state.emergency_floor_total = TimeManager.compute_emergency_floor(profile_budget)
    board = Board(time_to_play=profile_budget, build_history=False)
    board.player_worker.turns_left = 20

    for turn_count in (0, 19, 20, 59, 60):
        board.turn_count = turn_count
        if turn_count < 20:
            phase = "early"
        elif turn_count < 60:
            phase = "mid"
        else:
            phase = "late"
        for t_rem in (120.0, 60.0, 20.0, 10.0, state.emergency_floor_total + 0.5):
            for turns_left in (20, 5, 1):
                board.player_worker.turns_left = turns_left
                alloc, emerg = TimeManager.allocation(board, state, t_rem)
                lines.append(
                    f"| {turn_count} | {phase} | {t_rem:.2f} | {turns_left} | {alloc:.4f} | {emerg} |"
                )

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        choices=("strict", "local"),
        default="strict",
        help="strict: 240s + limit_resources (Linux default); local: 360s, no resource limits",
    )
    parser.add_argument("--games", type=int, default=8, help="Games (each swaps sides once)")
    parser.add_argument("--seed-start", type=int, default=42, help="Base seed for board randomness")
    parser.add_argument(
        "--limit-resources",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Override engine resource limits (default: True on Linux when profile=strict)",
    )
    parser.add_argument(
        "--play-time",
        type=int,
        default=None,
        help="Override per-player clock budget (default: 240 strict, 360 local)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress play_game stdout/stderr",
    )
    parser.add_argument(
        "--synthetic-table",
        action="store_true",
        help="Print synthetic TimeManager markdown table and exit (no games)",
    )
    args = parser.parse_args()

    if args.synthetic_table:
        print(synthetic_allocation_table(240.0))
        print()
        print(synthetic_allocation_table(360.0))
        return 0

    if args.profile == "strict":
        play_time = args.play_time if args.play_time is not None else 240
        limit_resources = (
            args.limit_resources if args.limit_resources is not None else platform.system() == "Linux"
        )
    else:
        play_time = args.play_time if args.play_time is not None else 360
        limit_resources = args.limit_resources if args.limit_resources is not None else False

    sys.path.insert(0, str(ROOT / "engine"))
    sys.path.insert(0, str(ROOT / "3600-agents"))
    from game.enums import ResultArbiter, WinReason
    from gameplay import play_game

    play_dir = os.path.join(str(ROOT), "3600-agents")

    y_att = y_cor = r_att = r_cor = 0
    y_wins = ties = 0
    sum_delta = 0.0
    n_delta = 0

    rel_timeout = rel_invalid = rel_crash = 0
    y_timeout_losses = 0

    with contextlib.ExitStack() as stack:
        if args.quiet:
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            stack.enter_context(contextlib.redirect_stderr(io.StringIO()))

        for g in range(args.games):
            random.seed(args.seed_start + g)
            yolanda_is_a = g % 2 == 0
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
                    limit_resources=limit_resources,
                    play_time_override=play_time,
                )
                sa, sb = _absolute_ab_scores(board)
                y_score, r_score = sa, sb
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
                    limit_resources=limit_resources,
                    play_time_override=play_time,
                )
                sa, sb = _absolute_ab_scores(board)
                y_score, r_score = sb, sa
                a_a, a_c = _stats_player_a(board)
                b_a, b_c = _stats_player_b(board)
                y_att += b_a
                y_cor += b_c
                r_att += a_a
                r_cor += a_c

            w = board.winner
            reason = board.win_reason

            if w == ResultArbiter.TIE:
                ties += 1
            elif (w == ResultArbiter.PLAYER_A and yolanda_is_a) or (
                w == ResultArbiter.PLAYER_B and not yolanda_is_a
            ):
                y_wins += 1

            delta = float(y_score - r_score)
            sum_delta += delta
            n_delta += 1

            if reason == WinReason.TIMEOUT:
                rel_timeout += 1
            elif reason == WinReason.INVALID_TURN:
                rel_invalid += 1
            elif reason in (WinReason.CODE_CRASH, WinReason.MEMORY_ERROR):
                rel_crash += 1

            if reason == WinReason.TIMEOUT and _yolanda_lost_ab(yolanda_is_a, w):
                y_timeout_losses += 1

    def rate(num: int, den: int) -> float:
        return float(num) / den if den else 0.0

    mean_delta = sum_delta / n_delta if n_delta else 0.0

    print(
        f"M2 competitive batch profile={args.profile} play_time={play_time} "
        f"limit_resources={limit_resources}"
    )
    print(f"games={args.games} seed_start={args.seed_start}")
    print(f"Yolanda wins={y_wins} ties={ties} baseline_wins={args.games - y_wins - ties}")
    print(f"Mean score delta (Yolanda - RandomSearchBaseline)={mean_delta:.3f}")
    print(
        f"Yolanda search: attempts={y_att} correct={y_cor} precision={rate(y_cor, y_att):.4f}"
    )
    print(
        f"RandomSearchBaseline search: attempts={r_att} correct={r_cor} precision={rate(r_cor, r_att):.4f}"
    )
    print(
        f"Reliability (all games): timeout={rel_timeout} invalid={rel_invalid} crash={rel_crash}"
    )
    print(f"Yolanda timeout losses={y_timeout_losses}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
